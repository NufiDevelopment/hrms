# Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, date_diff, format_date, get_link_to_form, getdate

from erpnext.setup.doctype.employee.employee import is_holiday

import hrms
from hrms.hr.utils import validate_active_employee, validate_dates


class OverlappingAttendanceRequestError(frappe.ValidationError):
	pass


class AttendanceRequest(Document):
	def validate(self):
		validate_active_employee(self.employee)
		validate_dates(self, self.from_date, self.to_date, False)
		self.validate_half_day()
		self.validate_request_overlap()
		self.validate_no_attendance_to_create()

	def validate_half_day(self):
		if self.half_day:
			if not getdate(self.from_date) <= getdate(self.half_day_date) <= getdate(self.to_date):
				frappe.throw(_("Half day date should be in between from date and to date"))

	def validate_no_attendance_to_create(self):
		attendance_warnings = self.get_attendance_warnings()
		attendance_request_days = date_diff(self.to_date, self.from_date) + 1
		if len(attendance_warnings) == attendance_request_days and not any(
			warning["action"] == "Overwrite" for warning in attendance_warnings
		):
			frappe.throw(
				title=_("No attendance records to create"),
				msg=_(
					"Please check if employee is on leave or attendance with the same status exists for selected day(s)."
				),
			)

	def validate_request_overlap(self):
		if not self.name:
			self.name = "New Attendance Request"

		Request = frappe.qb.DocType("Attendance Request")
		overlapping_request = (
			frappe.qb.from_(Request)
			.select(Request.name)
			.where(
				(Request.employee == self.employee)
				& (Request.docstatus < 2)
				& (Request.name != self.name)
				& (self.to_date >= Request.from_date)
				& (self.from_date <= Request.to_date)
			)
		).run(as_dict=True)

		if overlapping_request:
			self.throw_overlap_error(overlapping_request[0].name)

	def throw_overlap_error(self, overlapping_request: str):
		msg = _("Employee {0} already has an Attendance Request {1} that overlaps with this period").format(
			frappe.bold(self.employee),
			get_link_to_form("Attendance Request", overlapping_request),
		)

		frappe.throw(msg, title=_("Overlapping Attendance Request"), exc=OverlappingAttendanceRequestError)

	def on_submit(self):
		self.create_attendance_records()

	def on_cancel(self):
		attendance_list = frappe.get_all(
			"Attendance", {"employee": self.employee, "attendance_request": self.name, "docstatus": 1}
		)
		if attendance_list:
			for attendance in attendance_list:
				attendance_obj = frappe.get_doc("Attendance", attendance["name"])
				attendance_obj.cancel()

	def create_attendance_records(self):
		request_days = date_diff(self.to_date, self.from_date) + 1
		for day in range(request_days):
			attendance_date = add_days(self.from_date, day)
			if self.should_mark_attendance(attendance_date):
				self.create_or_update_attendance(attendance_date)

	def create_or_update_attendance(self, date: str):
		doc = self.get_attendance_doc(date)
		status = self.get_attendance_status(date)

		if doc:
			# update existing attendance, change the status
			old_status = doc.status

			if old_status != status:
				doc.db_set({"status": status, "attendance_request": self.name})
				if status == "Half Day":
					doc.db_set("half_day_status", "Absent")
					text = _(
						"Changed the status from {0} to {1} and Status for Other Half to {2} via Attendance Request"
					).format(frappe.bold(old_status), frappe.bold(status), frappe.bold("Absent"))
				else:
					text = _("Changed the status from {0} to {1} via Attendance Request").format(
						frappe.bold(old_status), frappe.bold(status)
					)
				doc.add_comment(comment_type="Info", text=text)

				frappe.msgprint(
					_("Updated status from {0} to {1} for date {2} in the attendance record {3}").format(
						frappe.bold(old_status),
						frappe.bold(status),
						frappe.bold(format_date(date)),
						get_link_to_form("Attendance", doc.name),
					),
					title=_("Attendance Updated"),
				)
		else:
			# submit a new attendance record
			doc = frappe.new_doc("Attendance")
			doc.employee = self.employee
			doc.attendance_date = date
			doc.shift = self.shift
			doc.company = self.company
			doc.attendance_request = self.name
			doc.status = status
			doc.half_day_status = "Absent" if status == "Half Day" else None
			doc.insert(ignore_permissions=True)
			doc.submit()

	def should_mark_attendance(self, attendance_date: str) -> bool:
		# Check if attendance_date is a holiday
		if not self.include_holidays and is_holiday(self.employee, attendance_date):
			frappe.msgprint(
				_("Attendance not submitted for {0} as it is a Holiday.").format(
					frappe.bold(format_date(attendance_date))
				)
			)
			return False

		# Check if employee is on leave
		if self.has_leave_record(attendance_date):
			frappe.msgprint(
				_("Attendance not submitted for {0} as {1} is on leave.").format(
					frappe.bold(format_date(attendance_date)), frappe.bold(self.employee)
				)
			)
			return False

		return True

	def has_leave_record(self, attendance_date: str) -> str | None:
		return frappe.db.exists(
			"Leave Application",
			{
				"employee": self.employee,
				"docstatus": 1,
				"from_date": ("<=", attendance_date),
				"to_date": (">=", attendance_date),
				"status": "Approved",
			},
		)

	def get_attendance_doc(self, attendance_date: str) -> str | None:
		attendance = frappe.db.exists(
			"Attendance",
			{
				"employee": self.employee,
				"attendance_date": attendance_date,
				"docstatus": ("!=", 2),
			},
		)
		return frappe.get_doc("Attendance", attendance) if attendance else None

	def get_attendance_status(self, attendance_date: str) -> str:
		if self.half_day and date_diff(getdate(self.half_day_date), getdate(attendance_date)) == 0:
			return "Half Day"
		elif self.reason == "Work From Home":
			return "Work From Home"
		else:
			return "Present"

	def status_unchanged(self, attendance_date):
		new_status = self.get_attendance_status(attendance_date)
		attendance_doc = self.get_attendance_doc(attendance_date)
		if attendance_doc and attendance_doc.status == new_status:
			return True
		return False

	def on_update(self):
		self.publish_update()

	def after_delete(self):
		self.publish_update()

	def publish_update(self):
		employee_user = frappe.db.get_value("Employee", self.employee, "user_id", cache=True)
		hrms.refetch_resource("hrms:my_attendance_requests", employee_user)
		hrms.refetch_resource("hrms:team_attendance_requests")

	@frappe.whitelist()
	def get_attendance_warnings(self) -> list:
		attendance_warnings = []
		request_days = date_diff(self.to_date, self.from_date) + 1

		for day in range(request_days):
			attendance_date = add_days(self.from_date, day)

			if not self.include_holidays and is_holiday(self.employee, attendance_date):
				attendance_warnings.append({"date": attendance_date, "reason": "Holiday", "action": "Skip"})
			elif self.has_leave_record(attendance_date):
				attendance_warnings.append({"date": attendance_date, "reason": "On Leave", "action": "Skip"})
			elif self.status_unchanged(attendance_date):
				attendance_warnings.append(
					{"date": attendance_date, "reason": "Attendance status unchanged", "action": "Skip"}
				)
			else:
				attendance = self.get_attendance_doc(attendance_date)
				if attendance:
					attendance_warnings.append(
						{
							"date": attendance_date,
							"reason": "Attendance already marked",
							"record": attendance.name,
							"action": "Overwrite",
						}
					)

		return attendance_warnings
