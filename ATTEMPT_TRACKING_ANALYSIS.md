# Quiz Attempt Tracking & Counting Analysis

## Overview
Quiz attempts are created, tracked, and displayed through a well-integrated system spanning MongoDB storage, service layer, and user interface. Each attempt is a complete session from quiz start to completion.

---

## 1. WHERE ATTEMPTS ARE CREATED & SAVED

### A. Creation Point: `routes/quiz.py` - `take_quiz()` [Lines 75-125]

**Location**: When a user clicks "Take Quiz" and the quiz starts

```python
# In take_quiz() route
attempt_id = db_service.create_quiz_attempt(user_id, quiz_id, selected_questions)
session[f'current_attempt_{quiz_id}'] = attempt_id
```

**What happens**:
- New attempt is created in MongoDB
- `attempt_id` is stored in Flask session for the duration of quiz-taking
- Selected questions are passed to track which questions were shown

---

### B. Creation Logic: `services/mongodb_service.py` - `create_quiz_attempt()` [Lines 506-524]

**Database method**:
```python
def create_quiz_attempt(self, user_id: str, quiz_id: str, questions: List[Dict]) -> str:
    """Create new quiz attempt"""
    
    attempt_data = {
        'user_id': user_id,
        'quiz_id': quiz_id,
        'question_ids': [q.get('id', '') for q in questions],
        'status': 'in_progress',
        'created_at': self.get_timestamp(),
        'updated_at': self.get_timestamp()
    }
    
    result = self._db['attempts'].insert_one(attempt_data)
    return str(result.inserted_id)
```

**Stored in MongoDB `attempts` collection** with fields:
- `user_id` - which student took it
- `quiz_id` - which quiz
- `question_ids` - list of questions shown
- `status` - tracks state: `in_progress` → `completed`
- `created_at` - when attempt started
- `updated_at` - last modification

**Important**: Attempts are created **immediately** when quiz starts, not saved to history until completed.

---

### C. Result Saving: `routes/quiz.py` - `submit_quiz()` [Lines 177-302]

**When**: After user submits answers at the end of quiz

**Multi-step save process**:

#### Step 1: Store result in memory (session) [Line 237]
```python
session[f'quiz_result_{attempt_id}'] = result_data
session.modified = True  # Force session save
```

#### Step 2: Save to Firebase/Database [Lines 265-302]
```python
# Update attempt status in MongoDB
db_service.save_quiz_result(user_id, quiz_id, attempt_id, result_data)

# Add to user's quiz history
history_entry = {
    'quiz_id': quiz_id,
    'quiz_name': quiz.get('name', 'Quiz'),
    'score': score_percentage,
    'correct': correct_count,
    'total_questions': total_questions,
    'marks_obtained': marks_obtained,
    'total_marks': total_marks,
    'time_taken': time_taken_seconds,
    'time_taken_display': time_taken_display,
    'timestamp': result_data['timestamp'],
    'attempt_id': attempt_id
}

db_service.add_to_quiz_history(user_id, history_entry)
```

#### Step 3: Session fallback [Lines 289-292]
```python
if 'quiz_history' not in session:
    session['quiz_history'] = []
session['quiz_history'].append(history_entry)
session.modified = True
```

---

### D. Database Update: `services/mongodb_service.py` - `save_quiz_result()` [Lines 526-628]

**Updates the attempt record**:
```python
self._db['attempts'].update_one(
    {'_id': ObjectId(attempt_id)},
    {
        '$set': {
            'status': 'completed',
            'completed_at': self.get_timestamp(),
            'result': sanitized_result,
            'updated_at': self.get_timestamp()
        }
    }
)
```

**Also updates user concept mastery** for adaptive learning.

---

## 2. WHERE ATTEMPT COUNT IS RETRIEVED

### A. Quiz History Endpoint: `routes/quiz.py` - `history()` [Lines 447-510]

**Route**: `/quiz/history`

**Retrieves all attempts for a user**:
```python
def history():
    user_id = session.get('user_id')
    history_raw = db_service.get_quiz_history(user_id)
    # Returns all quiz attempts...
```

**Database query**: `services/mongodb_service.py` - `get_quiz_history()` [Lines 669-682]
```python
def get_quiz_history(self, user_id: str) -> List[Dict]:
    """Get user's quiz history"""
    try:
        history = list(self._db['attempts'].find({'user_id': user_id}))
        # Returns all attempts for this user
        return history
    except Exception as e:
        print(f"Error getting history: {e}")
        return []
```

**What's returned**:
- All MongoDB `attempts` documents for a user
- Each attempt includes: `quiz_id`, `score`, `timestamp`, `result`, `question_ids`, etc.

### B. Summary Statistics Calculation

In `history()` route [Lines 475-495]:
```python
# Calculate summary stats
scores = [h['score'] for h in history if h['score'] > 0]
avg_score = round(sum(scores) / len(scores), 1) if scores else 0
best_score = round(max(scores), 1) if scores else 0
total_questions = sum(h['total'] for h in history)
```

**Stats displayed on history page**:
- **Total Attempts**: `len(history)` 
- **Average Score**: Average of all attempt scores
- **Best Score**: Highest score achieved
- **Total Questions**: Sum of all questions answered

---

## 3. WHERE ATTEMPT COUNT IS DISPLAYED TO USERS

### A. Quiz History Page: `templates/quiz/history.html` [Lines 1-250]

**Summary Cards** [Lines 27-53]:
```html
<!-- Total Attempts Card -->
<div class="card bg-primary text-white stat-card">
    <div class="card-body text-center">
        <h3>{{ history|length }}</h3>
        <small>Total Attempts</small>
    </div>
</div>

<!-- Average Score -->
<h3>{{ avg_score }}%</h3>

<!-- Best Score -->
<h3>{{ best_score }}%</h3>

<!-- Total Questions Answered -->
<h3>{{ total_questions }}</h3>
```

**Attempt List** [Lines 100-140]:
- Displays each attempt in a table row
- Shows: Quiz name, date, score, marks (e.g., "15/20"), grade
- Each row has "View Results" button linking to detailed results

### B. Quiz Results Page: `templates/quiz/results.html` [Lines 1-150]

**Displays individual attempt result**:
```html
<!-- Score Display -->
<span class="display-5">{{ result.get('marks_obtained', result.get('correct', 0))|int }}</span>
<span class="fs-3"> / </span>
<span class="display-5">{{ result.get('total_marks', result.get('total_questions', 0))|int }}</span>

<!-- Correct/Total -->
<span class="text-success">{{ result.get('correct', 0)|int }}</span> / 
<span>{{ result.get('total_questions', 0)|int }}</span>
```

### C. Quiz Take Page: `templates/quiz/take.html` [Lines 61-75]

**During quiz - question counter**:
```html
<!-- Question Counter -->
<div class="alert alert-info mb-4">
    <div class="d-flex justify-content-between">
        <span><strong id="questionCounter">Question 1</strong> of <strong>{{ questions|length }}</strong></span>
        <span><strong id="answeredCount">0</strong> answered</span>
    </div>
</div>
```

This shows real-time progress during the quiz (not cumulative attempts, but current attempt).

---

## 4. POTENTIAL DUPLICATE CREATION LOGIC

### ⚠️ ISSUE IDENTIFIED: Dual Attempt Creation

#### Location 1: `create_quiz_attempt()` - creates in MongoDB
```python
# routes/quiz.py line 115
attempt_id = db_service.create_quiz_attempt(user_id, quiz_id, selected_questions)
```

#### Location 2: `add_to_quiz_history()` - adds to user's array
```python
# routes/quiz.py line 283
db_service.add_to_quiz_history(user_id, history_entry)
```

**Potential problem**: 
- The `attempts` collection stores full attempt records
- The `users.quiz_history` array stores a duplicate summary
- If user document's `quiz_history` array grows unbounded, it could cause issues

**Current mitigation**: No visible issue yet, but worth monitoring.

---

## 5. DATA FLOW SUMMARY

```
┌─────────────────────────────────────────────────────────────┐
│ USER STARTS QUIZ (take_quiz route)                          │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ create_quiz_attempt() - Insert into attempts collection     │
│ - user_id, quiz_id, question_ids, status='in_progress'    │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ STORE attempt_id IN SESSION for quiz duration              │
│ session[f'current_attempt_{quiz_id}'] = attempt_id         │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
         ┌─────────────────┐
         │ USER TAKES QUIZ │
         └────────┬────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ USER SUBMITS ANSWERS (submit_quiz route)                   │
└──────────────────┬──────────────────────────────────────────┘
                   │
        ┌──────────┴──────────┐
        ▼                     ▼
    IN SESSION           IN DATABASE
    session[            save_quiz_result()
    quiz_result_X]    - Update attempts.status 
                      - Store result details
                      - Update user.concept_mastery
                           ▼
                      add_to_quiz_history()
                      - Add to users.quiz_history[]
        │                     │
        └──────────┬──────────┘
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ REDIRECT TO RESULTS PAGE (/results/<quiz_id>/<attempt_id>)│
│ - Retrieve from session (if just completed)                │
│ - Or from database (if viewing old results)               │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ Display results with weak/strong concepts & recommendations│
└─────────────────────────────────────────────────────────────┘
```

---

## 6. KEY COLLECTIONS & SCHEMA

### MongoDB Collections:

#### `attempts` - Full attempt records
```javascript
{
  _id: ObjectId,
  user_id: "user_1",
  quiz_id: "quiz_1",
  question_ids: ["q_1", "q_2", "q_3"],
  status: "completed", // "in_progress" | "completed"
  created_at: "2024-03-27T10:00:00",
  updated_at: "2024-03-27T10:05:00",
  completed_at: "2024-03-27T10:05:00",
  result: {
    score: 80.5,
    correct: 8,
    total_questions: 10,
    marks_obtained: 8,
    total_marks: 10,
    concept_performance: { "Algebra": 0.75, "Geometry": 0.9 },
    details: [...]
  }
}
```

#### `users` - User profile (includes quiz history array)
```javascript
{
  _id: ObjectId,
  email: "user@example.com",
  quiz_history: [
    {
      quiz_id: "quiz_1",
      quiz_name: "Math Quiz",
      score: 80.5,
      attempt_id: "attempt_1",
      timestamp: "2024-03-27T10:00:00",
      ...
    }
  ],
  concept_mastery: { "Algebra": 0.75, "Geometry": 0.9 }
}
```

---

## 7. ATTEMPT RETRIEVAL METHODS

| Method | Collection | Purpose | Returns |
|--------|-----------|---------|---------|
| `get_quiz_history(user_id)` | `attempts` | Get all user attempts | List of attempt docs |
| `get_recent_quizzes(user_id, limit)` | `attempts` | Get recent N attempts | Top N attempts sorted by date |
| `get_quiz_result(user_id, quiz_id, attempt_id)` | `attempts` | Get specific result | Single attempt with result |
| `add_to_quiz_history(user_id, entry)` | `users` | Add to user.quiz_history[] | Pushes to array |

---

## 8. OBSERVATIONS & NOTES

✅ **Working Well**:
- Attempts are properly created/saved to MongoDB
- Attempt count is correctly calculated from `attempts` collection
- Display shows attempt count in summary statistics
- Results are retrievable and displayed correctly
- Session backup works for demo mode

⚠️ **Potential Issues**:
1. **Dual storage**: Data stored in both `attempts` collection AND `users.quiz_history[]` array
   - Could cause inconsistency if one fails
   - Array growth in user document could eventually impact performance
   
2. **Session reliance**: Results depend on session for immediate display
   - Demo mode works via session storage
   - Long sessions might expire before results are viewed

3. **No explicit attempt numbering**: Attempts aren't numbered/indexed (e.g., "Attempt 1 of 5")
   - Currently just shows total count
   - Could be added via `attempt_number` field in future

---

## 9. RECOMMENDATIONS

1. **Add attempt number field**:
   ```python
   def add_to_quiz_history(self, user_id: str, history_entry: Dict):
       attempt_number = existing_history_length + 1
       history_entry['attempt_number'] = attempt_number
   ```

2. **Consider archiving old quiz_history array**:
   - Move to separate `quiz_history_archive` collection after N attempts
   - Keeps user document lean

3. **Add indexes for performance**:
   - Already has: `attempts: [('user_id', 1), ('quiz_id', 1)]` ✓
   - Consider: `attempts: [('user_id', 1), ('created_at', -1)]` for sorting

4. **Add attempt view counter**:
   - Track how many times each attempt result was viewed
   - Could indicate re-studying patterns
