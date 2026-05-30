# Local MongoDB Setup Guide

## Quick Start

Your application is now configured to use **localhost:27017** (local MongoDB) instead of cloud database.

### Installation & Setup

#### Option 1: Windows (Using MongoDB Community Edition)

1. **Download MongoDB Installer**
   - Visit: https://www.mongodb.com/try/download/community
   - Select Version: Latest (Stable)
   - Select Platform: Windows
   - Click Download

2. **Install MongoDB**
   - Run the installer (.msi file)
   - Choose "Run as Administrator"
   - Keep default installation settings
   - Check "Install MongoDB as a Service" (recommended)
   - Finish installation

3. **Start MongoDB Service**
   - MongoDB should start automatically if installed as service
   - To verify, open PowerShell and run:
     ```powershell
     mongosh
     ```
   - Or for older versions:
     ```powershell
     mongo
     ```
   - You should see the MongoDB shell prompt

#### Option 2: Windows (Using Chocolatey - Faster)

If you have Chocolatey installed:
```powershell
choco install mongodb-community
```

#### Option 3: Docker (Easiest)

If you have Docker installed:
```powershell
docker run -d -p 27017:27017 --name mongodb mongo:latest
```

### Verify Connection

Test if MongoDB is running by running your app:

```bash
python app.py
```

You should see:
```
[MongoDB] ✓ Connected to localhost:27017
```

### Database Info

- **Connection String**: `mongodb://localhost:27017/quiz_generator`
- **Database Name**: `quiz_generator`
- **Default Port**: `27017`
- **No Password Required** (local development)

### Stopping MongoDB

**Windows Service:**
```powershell
# Stop service
net stop MongoDB
# Start service
net start MongoDB
```

**Docker:**
```bash
docker stop mongodb
docker start mongodb
```

### Troubleshooting

If you see: `[MongoDB] ⚠️  Cannot connect to localhost:27017`

1. Check if MongoDB is running:
   ```powershell
   Get-Service MongoDB
   ```

2. If not running, start it:
   ```powershell
   # For Windows Service
   net start MongoDB
   
   # Or check Task Manager for "mongod" process
   ```

3. Check if port 27017 is in use:
   ```powershell
   netstat -ano | findstr :27017
   ```

4. View MongoDB logs (Windows Service):
   ```powershell
   Get-Content "C:\Program Files\MongoDB\Server\7.0\log\mongod.log" -Tail 20
   ```

---

**That's it!** Your app will now connect to the local MongoDB on startup.
