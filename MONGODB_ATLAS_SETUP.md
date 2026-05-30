# MongoDB Atlas Connection Troubleshooting Guide

## ⚠️ Current Issue

Your new MongoDB Atlas Cluster0 (cluster0.qsenboa.mongodb.net) is not reachable.

**Error:** `No replica set members found yet, Timeout: 30.0s`

This means your computer **cannot reach the MongoDB Atlas servers** due to:
- Firewall blocking the connection
- Network restrictions (corporate network, ISP blocks, etc.)
- VPN interfering with connection
- IP not whitelisted in MongoDB Atlas

---

## ✅ Quick Fix Checklist

### Step 1: Whitelist Your IP in MongoDB Atlas

**IMPORTANT:** This is the most common solution

1. Go to **https://cloud.mongodb.com/**
2. Login with your account
3. Click on **Cluster0**
4. Go to **Security** → **Network Access**
5. Click **Add IP Address**
6. Choose one of:
   - **Add Current IP** (if your IP is static)
   - **Allow Access from Anywhere** (0.0.0.0/0) - easiest for testing
7. Click **Confirm**
8. Wait 2-3 minutes for the change to take effect

**Return here after whitelisting:** Test with `python test_atlas_connection.py`

---

### Step 2: Check Your Internet Connection

```powershell
# Test if you can reach Google
ping google.com

# Test HTTPS connectivity
Invoke-WebRequest "https://www.mongodb.com" -UseBasicParsing
```

If these fail, fix your internet first.

---

### Step 3: Check/Disable Windows Firewall

```powershell
# Open Windows Firewall
wf.msc

# Then create outbound rules for MongoDB Atlas
```

Or temporarily disable firewall to test:
```powershell
# Disable Windows Defender Firewall
Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled $false

# To re-enable later:
Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled $true
```

---

### Step 4: Check if VPN is Enabled

- Disable any VPN if you're using one
- Some VPNs block MongoDB Atlas ports
- Test without VPN first

---

### Step 5: Check Antivirus/Corporate Firewall

If you're on a corporate network:
- Contact your IT department
- Ask them to whitelist MongoDB Atlas domain: `*.qsenboa.mongodb.net`
- Ask them to allow outbound HTTPS (port 443) and MongoDB (port 27017)

---

## 📋 Your Current Configuration

```
MongoDB Atlas Cluster: Cluster0
Database Name: Quizgenerator
Username: krishalmodi2345_db_user
Password: c35p04qQXnVk9VaU
Collections to be created:
  • users (signups)
  • quizzes (quiz questions)
  • questions (individual questions)
  • documents (uploaded materials)
  • attempts (quiz responses)
  • concepts (knowledge concepts)
```

---

## 🧪 Test Connection After Fixing IP Whitelist

Once you've whitelisted your IP, run:

```powershell
cd c:\Users\krish\Projects\QuizGenerator
.\.venv\Scripts\python.exe test_atlas_connection.py
```

You should see:
```
✅ MONGODB ATLAS CONNECTION SUCCESSFUL!
Database: Quizgenerator
Collections Created: 6
```

---

## 🚀 After Successful Connection

1. Your database **Quizgenerator** will be automatically created
2. All 6 collections will be created:
   - `users` - your signup data
   - `quizzes` - quiz questions
   - `questions` - individual questions
   - `documents` - uploaded files
   - `attempts` - quiz responses
   - `concepts` - knowledge concepts

3. Then run the Flask app:
```powershell
python app.py
```

4. View your data in MongoDB Atlas:
   - Go to https://cloud.mongodb.com/
   - Click Cluster0 → Browse Collections
   - Select "Quizgenerator" database
   - See all your data in real-time

---

## 📞 If Still Not Working

If you've done all steps and it still doesn't work:

1. **Check MongoDB Atlas Status:** https://status.mongodb.com/
2. **Check Cluster Status:** Go to MongoDB Atlas → Cluster0 → Check the status (should be green)
3. **Verify Credentials:** Go to Database Access in MongoDB Atlas → Verify user exists
4. **Test from Different Network:** Try from mobile hotspot to isolate the issue
5. **Contact MongoDB Support:** https://www.mongodb.com/support/contact

---

## 💡 Alternative: Use Local MongoDB Instead

If MongoDB Atlas connection persists:

1. Install MongoDB Community locally: https://www.mongodb.com/try/download/community
2. Start MongoDB
3. Update .env: `MONGODB_URI=mongodb://localhost:27017/Quizgenerator`
4. Run: `python app.py`

---

**STATUS:** ⏳ Waiting for your IP whitelist in MongoDB Atlas
**NEXT STEP:** Whitelist your IP → Run test_atlas_connection.py → Run app.py

