"""
Shared service instances - Created once at app startup, imported by all routes.
This avoids creating multiple MongoDB connections and speeds up the app.
"""

from services.mongodb_service import MongoDBService
from services.quiz_service import QuizService
from services.bandit_service import BanditService
from services.progress_service import ProgressService
from services.document_service import DocumentService
from services.concept_service import ConceptService
from services.question_generator import QuestionGenerator

# Create single MongoDB instance first
db_service = MongoDBService()

# Create other services and inject the shared db_service
quiz_service = QuizService(db_service=db_service)
progress_service = ProgressService(db_service=db_service)

# Services that don't need db_service or manage it themselves
bandit_service = BanditService()
document_service = DocumentService()
concept_service = ConceptService()
question_generator = QuestionGenerator()
