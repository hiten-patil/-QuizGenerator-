# Quiz Generator

An intelligent adaptive quiz generation system that creates personalized quizzes from lecture notes using AI, Knowledge Graphs, and Multi-Armed Bandit algorithms.

## 🎯 Features

### For Students
- **Take Adaptive Quizzes**: Questions adapt to your performance in real-time
- **Multiple Question Types**: Multiple choice, True/False, and short answer questions
- **Knowledge Graph Visualization**: See how concepts relate to each other
- **Progress Tracking**: Monitor your learning progress and quiz history
- **Performance Analytics**: View detailed results and identify areas for improvement

### For Instructors
- **AI-Powered Quiz Generation**: Upload documents (PDF, DOCX, TXT) and generate quizzes automatically
- **Concept Extraction**: Automatic identification of key concepts from lecture materials
- **Question Customization**: Edit and refine generated questions
- **Student Analytics**: Track class performance and identify struggling students
- **Quiz Management**: Create, edit, and manage multiple quizzes with unique access codes

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- MongoDB Atlas account (or local MongoDB)
- Git (optional)

### Installation

1. **Clone or download the project**
   ```bash
   git clone <repository-url>
   cd QuizGenerator
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv .venv
   
   # On Windows PowerShell
   .\.venv\Scripts\Activate.ps1
   
   # On Windows CMD
   .\.venv\Scripts\activate.bat
   
   # On Linux/Mac
   source .venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   python -m spacy download en_core_web_sm
   ```

4. **Configure MongoDB**
   - Create a MongoDB Atlas account at [mongodb.com/cloud/atlas](https://www.mongodb.com/cloud/atlas)
   - Create a cluster and database
   - Create a database user with read/write permissions
   - Get your connection string (mongodb+srv://username:password@cluster...)

5. **Set up environment variables**
   - Copy `.env.example` to `.env` (or create `.env` file)
   - Fill in your MongoDB configuration:
     ```env
     MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/?appName=Cluster0
     SECRET_KEY=your_secret_key_here
     ```

6. **Verify setup**
   ```bash
   python check_setup.py
   ```

7. **Run the application**
   ```bash
   python app.py
   ```
   
   Or use the quick start scripts:
   - Windows: Double-click `start.bat` or run `.\start.ps1`
   - Or simply: `python app.py`

8. **Access the application**
   - Open your browser and go to: http://127.0.0.1:5000
   - Create an account and start using the system!

## 📁 Project Structure

```
QuizGenerator/
├── app.py                      # Main Flask application
├── requirements.txt            # Python dependencies
├── check_setup.py             # Setup verification script
├── start.bat / start.ps1      # Quick start scripts
├── .env                       # Environment variables (MongoDB URI)
├── MONGODB_SETUP.md          # Quick MongoDB setup guide
├── MONGODB_MIGRATION.md      # Detailed migration documentation
│
├── config/
│   └── __init__.py            # Config module
│
├── routes/                    # Flask route blueprints
│   ├── auth.py               # Authentication routes
│   ├── dashboard.py          # Student dashboard routes
│   ├── instructor.py         # Instructor routes
│   ├── quiz.py              # Quiz taking routes
│   └── api.py               # API endpoints
│
├── services/                 # Business logic services
│   ├── mongodb_service.py   # MongoDB database operations (NEW)
│   ├── document_service.py  # Document processing
│   ├── concept_service.py   # Concept extraction
│   ├── question_generator.py # Question generation
│   ├── quiz_service.py      # Quiz management
│   ├── bandit_service.py    # Multi-Armed Bandit algorithm
│   ├── adaptive_quiz_engine.py # Adaptive quiz logic
│   └── difficulty_controller.py # Difficulty management
│
├── static/                   # Static assets
│   ├── css/
│   └── js/
│
├── templates/                # HTML templates
│   ├── auth/                # Login, signup pages
│   ├── dashboard/           # Student pages
│   ├── instructor/          # Instructor pages
│   ├── quiz/                # Quiz pages
│   └── errors/              # Error pages
│
└── uploads/                  # Uploaded documents (auto-created)
```

## 🔧 Configuration

### MongoDB Setup
1. Go to [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)
2. Create an account or log in
3. Create a new cluster:
   - Choose cloud provider and region
   - Select cluster tier (Free tier recommended for testing)
4. Create **Database User**:
   - Go to Security → Database Access
   - Create a new database user with password
5. Whitelist **IP Address**:
   - Go to Security → Network Access
   - Add your IP address (or 0.0.0.0/0 for development)
6. Get your **Connection String**:
   - Go to your cluster → Connect
   - Choose "Connect your application"
   - Copy the connection string
   - Replace `<password>` with your database user password

### Environment Variables
All configuration is done through the `.env` file. Required variables:
- `MONGODB_URI`: Your MongoDB Atlas connection string
- `SECRET_KEY`: Flask secret key (generate with `python -c "import secrets; print(secrets.token_hex(32))"`)

Optional:
- `OPENAI_API_KEY`: For ChatGPT-quality questions
- `GEMINI_API_KEY`: For Google Gemini questions

For detailed MongoDB setup instructions, see [MONGODB_SETUP.md](MONGODB_SETUP.md)

### For Students

1. **Sign Up / Login**
   - Create an account with email and password
   - Your role is automatically set to "student"

2. **Find and Take Quizzes**
   - Enter a quiz code provided by your instructor
   - Answer questions one at a time
   - Questions adapt based on your performance

3. **View Your Progress**
   - Check your quiz history
   - View detailed results and explanations
   - See the knowledge graph of concepts

### For Instructors

1. **Sign Up as Instructor**
   - Create an account
   - Your role can be changed in the database (set `role: "instructor"`)

2. **Upload Documents**
   - Go to Instructor Dashboard → Upload Document
   - Upload PDF, DOCX, or TXT files
   - System extracts text and concepts automatically

3. **Generate Quizzes**
   - Select a document
   - Choose number of questions and types
   - Review and edit generated questions
   - Publish with a unique quiz code

4. **Share Quiz Code**
   - Give the quiz code to your students
   - Students enter the code to access the quiz

5. **View Analytics**
   - See student performance
   - Identify difficult concepts
   - Track class progress

## 🧠 Technical Details

### AI & ML Components
- **NLP**: Spacy for text processing and entity recognition
- **Transformers**: BERT-based models for question generation
- **KeyBERT**: Keyword extraction from documents
- **Knowledge Graphs**: NetworkX for concept relationships
- **Adaptive Learning**: Thompson Sampling (Multi-Armed Bandit)

### Multi-Armed Bandit Algorithm
The system uses Thompson Sampling to:
- Select questions based on student performance
- Balance exploration (new concepts) and exploitation (mastery)
- Adapt difficulty in real-time
- Maximize learning efficiency

### Question Generation
1. **Document Processing**: Extract clean text from PDFs/DOCX
2. **Concept Extraction**: Identify key terms and concepts
3. **Question Generation**: Use AI to create multiple question types
4. **Quality Filtering**: Ensure questions are valid and meaningful

## 🛠️ Maintenance

### Reset Database
To clear all data and start fresh:
```bash
python delete_database.py
```
**Warning**: This deletes ALL data including users, quizzes, and documents!

### Check System Health
Run the verification script:
```bash
python check_setup.py
```

### Update Dependencies
```bash
pip install --upgrade -r requirements.txt
```

## 🐛 Troubleshooting

### Common Issues

**1. ModuleNotFoundError: No module named '...'**
```bash
pip install -r requirements.txt
```

**2. Firebase connection error**
- Check `.env` file has correct values
- Verify `config/firebase-admin-sdk.json` exists
- Ensure Firebase Database URL is correct

**3. Spacy model not found**
```bash
python -m spacy download en_core_web_sm
```

**4. Port already in use**
- Change port in `app.py`: `app.run(debug=True, port=5001)`
- Or kill process using port 5000

**5. Upload folder permission error**
- Ensure `uploads/` folder exists and is writable
- On Linux/Mac: `chmod 755 uploads/`

## 📝 Development

### Running in Development Mode
```bash
# With auto-reload
python app.py

# With specific port
# Edit app.py and change: app.run(debug=True, port=5001)
```

### Running Tests
```bash
pytest test_quiz_system.py
pytest test_firebase_data.py
```

### Code Structure
- **Routes**: Handle HTTP requests and responses
- **Services**: Business logic and external integrations
- **Templates**: Jinja2 HTML templates with Bootstrap 5
- **Static**: CSS, JavaScript, and assets

## 🔒 Security Notes

- Never commit `.env` or `firebase-admin-sdk.json` to version control
- Use environment variables for all sensitive data
- Configure Firebase security rules for production
- Use HTTPS in production
- Set strong `SECRET_KEY` for session encryption

## 📚 Technologies Used

- **Backend**: Flask (Python)
- **Database**: Firebase Realtime Database
- **Authentication**: Firebase Authentication
- **AI/ML**: Transformers, Spacy, NLTK, PyTorch
- **Frontend**: Bootstrap 5, JavaScript
- **Document Processing**: PDFPlumber, python-docx
- **Visualization**: PyVis (Knowledge Graphs), Chart.js

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

## 📧 Support

For issues or questions:
- Check the troubleshooting section above
- Run `python check_setup.py` to diagnose problems
- Review error messages in terminal output

## 🎉 Credits

Built with ❤️ using modern AI and web technologies.

---

**Ready to start?** Run `python check_setup.py` to verify your setup, then `python app.py` to launch the application!
