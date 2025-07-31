#!/bin/bash

echo "🚀 HRMS Development Version Rebuild"
echo "=================================="

# Check if we're in the right directory
if [ ! -f "docker/docker-compose.yml" ]; then
    echo "❌ Error: Please run this script from the project root directory"
    exit 1
fi

echo "📦 Stopping development container..."
docker compose -f docker/docker-compose.yml stop hrms-dev

echo "🗑️  Removing old development image..."
docker rmi docker-hrms-dev 2>/dev/null || echo "No old image to remove"

echo "🔨 Building new development version..."
docker compose -f docker/docker-compose.yml build --no-cache hrms-dev

if [ $? -eq 0 ]; then
    echo "✅ Build successful!"
else
    echo "❌ Build failed!"
    exit 1
fi

echo "🚀 Starting development version..."
docker compose -f docker/docker-compose.yml up -d hrms-dev

echo "⏳ Waiting for service to be ready..."
sleep 30

echo "🔍 Checking service status..."
if curl -f -s http://localhost:3000 > /dev/null; then
    echo "✅ Development version is running!"
    echo "🌐 Access URL: http://localhost:3000"
    echo "📝 Login: admin / admin"
else
    echo "❌ Service is not responding"
    echo "📋 Checking logs..."
    docker compose -f docker/docker-compose.yml logs --tail=20 hrms-dev
fi

echo ""
echo "📊 Container Status:"
docker compose -f docker/docker-compose.yml ps hrms-dev 