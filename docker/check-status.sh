#!/bin/bash

echo "=== HRMS DUAL VERSION STATUS CHECK ==="
echo ""

echo "🔍 Checking Stable Version (Port 80)..."
if curl -s -o /dev/null -w "%{http_code}" http://localhost:80 | grep -q "200"; then
    echo "✅ Stable Version (Port 80): RUNNING"
else
    echo "⏳ Stable Version (Port 80): Still initializing..."
fi

echo ""
echo "🔍 Checking Development Version (Port 3000)..."
if curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 | grep -q "200"; then
    echo "✅ Development Version (Port 3000): RUNNING"
else
    echo "⏳ Development Version (Port 3000): Still initializing..."
fi

echo ""
echo "📊 Container Status:"
docker compose -f docker/docker-compose.yml ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo "🌐 Access URLs:"
echo "   Stable Version:     http://localhost:80"
echo "   Development Version: http://localhost:3000"
echo ""
echo "📝 Login Credentials:"
echo "   Username: admin"
echo "   Password: admin" 