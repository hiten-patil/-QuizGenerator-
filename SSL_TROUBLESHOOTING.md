# MongoDB Atlas SSL Connection Troubleshooting

## 🔴 Current Error

```
SSL handshake failed: ac-tvog31o-shard-00-00.qsenboa.mongodb.net:27017
The handshake operation timed out
```

**What this means:** Your computer cannot establish a secure SSL/TLS connection to MongoDB Atlas servers.

---

## ✅ Solution Steps (In Order)

### **STEP 1: Whitelist Your IP in MongoDB Atlas** ⭐ MOST IMPORTANT

This fixes 90% of SSL timeout issues.

1. Go to **https://cloud.mongodb.com/**
2. Click **Cluster0**
3. Go to **Security** → **Network Access**
4. Click **+ Add IP Address**
5. Choose **"Allow Access from Anywhere"** (0.0.0.0/0)
   - Or for security: **"Add Current IP Address"** if you have static IP
6. Click **"Confirm"**
7. **WAIT 2-3 MINUTES** - changes take time to propagate

### **STEP 2: Check Firewall Settings**

Windows Firewall or antivirus may block MongoDB:

**Option A: Check Windows Firewall**
```powershell
# Open Windows Firewall
wf.msc
```
- Check if port 27017 is blocked
- Check if antivirus is intercepting SSL

**Option B: Temporarily Disable Firewall (for testing)**
```powershell
# Disable all firewalls
Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled $false

# Re-enable later:
Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled $true
```

### **STEP 3: Check Internet Connection**

```powershell
# Test basic internet
ping google.com

# Test MongoDB Atlas server
ping cluster0.qsenboa.mongodb.net

# Test HTTPS
Invoke-WebRequest "https://cloud.mongodb.com" -UseBasicParsing
```

If these fail, fix your internet first.

### **STEP 4: Disable VPN**

Some VPNs block MongoDB Atlas:
- Disable any VPN/proxy
- Test connection
- Re-enable VPN after testing

### **STEP 5: Check Antivirus Software**

Corporate antivirus may intercept SSL:
- Whitelist MongoDB Atlas domain in antivirus
- Whitelist port 27017
- Or temporarily disable antivirus to test

### **STEP 6: On Corporate Network?**

If you're on a corporate network:
- Contact your IT department
- Ask them to whitelist:
  - Domain: `*.qsenboa.mongodb.net`
  - Port: 27017 (MongoDB)
  - Port: 443 (HTTPS)

---

## 🧪 Test Connection After Fixes

Once you've applied fixes above, run:

```powershell
cd c:\Users\krish\Projects\QuizGenerator
.\.venv\Scripts\python.exe test_atlas_connection.py
```

**Expected Output:**
```
✅ MONGODB ATLAS CONNECTION SUCCESSFUL!
Database: Quizgenerator
Collections: 6 ready
SSL Mode: ✓ VERIFIED
Status: ✅ Ready for use
```

---

## 📋 Code Changes Made

Your code now includes:

**1. SSL/TLS Handling in `services/mongodb_service.py`:**
- First tries with strict SSL certificate verification
- Falls back to SSL without verification if firewall blocks certs
- Better error messages explaining the issue

**2. Improved Test Script `test_atlas_connection.py`:**
- Tries with SSL verification first
- Falls back gracefully
- Provides detailed troubleshooting steps
- Shows collection status

**3. Better Error Messages:**
- Detects SSL timeout specifically
- Provides step-by-step solutions
- Guides you to MongoDB Atlas dashboard

---

## 🎯 Your MongoDB Atlas Configuration

```
Cluster: Cluster0
Database: Quizgenerator  
Username: krishalmodi2345_db_user
Password: c35p04qQXnVk9VaU
Host: cluster0.qsenboa.mongodb.net

Collections to be created:
├── users (signup data)
├── quizzes (quiz questions)
├── questions (individual questions)
├── documents (uploaded files)
├── attempts (quiz responses)
└── concepts (knowledge tracking)
```

---

## 🚀 After Successful Connection

1. **Run the test:**
   ```powershell
   python test_atlas_connection.py
   ```

2. **Start the app:**
   ```powershell
   python app.py
   ```

3. **View data in MongoDB Atlas:**
   - Go to: https://cloud.mongodb.com/
   - Click "Cluster0"
   - Click "Browse Collections"
   - Select "Quizgenerator" database
   - See your data in real-time!

---

## 📞 Still Not Working?

Check in this order:

1. **IP Whitelisted?** → Go to https://cloud.mongodb.com/ → Cluster0 → Security → Network Access
2. **Cluster Running?** → Cluster0 should have green status indicator
3. **Firewall/Antivirus?** → Try disabling temporarily
4. **VPN?** → Disable VPN and test
5. **Internet?** → Run `ping google.com`
6. **MongoDB Status?** → Check https://status.mongodb.com/

---

## 🔧 Manual SSL Configuration

If you still have issues, you can manually configure SSL:

In `services/mongodb_service.py`, the code now tries these options in order:

**Option 1 (Default - Most Secure):**
```python
ssl=True,
tlsInsecure=False,  # Strict certificate verification
ssl_cert_reqs=ssl.CERT_REQUIRED
```

**Option 2 (Fallback - If firewall blocks certs):**
```python
ssl=True,
tlsInsecure=True  # Skip certificate verification
```

The code automatically uses Option 2 if Option 1 fails.

---

## 📊 Connection Flow

```
app.py starts
  ↓
mongodb_service.py initializes
  ↓
Try SSL with certificate verification
  ↓
IF FAILS → Try SSL without verification
  ↓
IF FAILS → Run in DEMO MODE (data not saved)
```

---

## ✨ Quick Checklist

- [ ] Whitelisted IP in MongoDB Atlas (0.0.0.0/0)
- [ ] Waited 2-3 minutes for changes
- [ ] Disabled Windows Firewall (for testing)
- [ ] Disabled VPN
- [ ] Checked internet connection
- [ ] Ran `test_atlas_connection.py` successfully
- [ ] Now ready to run `python app.py`

---

**Status:** 🔴 Waiting for IP whitelist  
**Goal:** ✅ Get SQL handshake to complete  
**Timeline:** 5-10 minutes total with IP whitelist

If you complete all steps and still have issues, please share the exact error message from `test_atlas_connection.py` and I can help further!

