import asyncio
import sys
from datetime import datetime, timedelta

# Mock objects to simulate SQLAlchemy models and results
class MockWorkout:
    def __init__(self, id, started_at):
        self.id = id
        self.started_at = started_at
        self.sets = []

class MockExercise:
    def __init__(self, id, name):
        self.id = id
        self.name = name

class MockWorkoutSet:
    def __init__(self, id, workout_id, weight, reps, duration_seconds=None, set_order=0):
        self.id = id
        self.workout_id = workout_id
        self.exercise_id = 1
        self.weight = weight
        self.reps = reps
        self.duration_seconds = duration_seconds
        self.set_order = set_order
        self.set_label = None
        self.is_pr = False
        self.exercise = MockExercise(1, "Bench Press")

# Function to test (copied from exercise_stats.py for isolation)
def _brzycki_1rm(weight: float, reps: int) -> float:
    if reps <= 0:
        return 0.0
    if reps >= 37:
        return weight * 1.1
    return weight * (36 / (37 - reps))

async def reproduce():
    print("Testing _brzycki_1rm logic...")
    try:
        # Test case 1: Normal values
        print(f"100x10: {_brzycki_1rm(100.0, 10)}")
        
        # Test case 2: High reps
        print(f"100x37: {_brzycki_1rm(100.0, 37)}")
        
        # Test case 3: Zero reps
        print(f"100x0: {_brzycki_1rm(100.0, 0)}")

        # Test case 4: None values (simulating what might happen if database returns None and we cast it)
        # In the code: float(row.weight) if row.weight else 0
        # If row.weight is None, it becomes 0.
        print(f"0x10: {_brzycki_1rm(0.0, 10)}")
        print(f"100x0: {_brzycki_1rm(100.0, 0)}")
        
    except Exception as e:
        print(f"Error in calculation: {e}")

    print("\nSimulating logic flow...")
    # Simulate the logic in exercise_stats.py
    
    # 1. PRs logic
    # best_weight = float(prs.best_weight) if prs.best_weight else None
    # If best_weight is None, that's fine.
    
    # 2. Volume logic
    # vol = w * r
    # w = float(row.weight) if row.weight else 0
    # r = int(row.reps) if row.reps else 0
    # This seems safe.

    # 3. Progression logic
    # est = _brzycki_1rm(float(row.weight), int(row.reps))
    # Query: WorkoutSet.weight.isnot(None), WorkoutSet.reps.isnot(None)
    # So weight and reps should be values.
    
    print("Attempting to reproduce with potential edge cases...")
    
    # Hypothesis: Maybe one of the queries returns something unexpected when there are no sets?
    # behavior of `one()` vs `scalar_one()`
    
    # Let's verify Brzycki with negative numbers? (Shouldn't happen in DB usually but possible)
    try:
        print(f"Negative reps: {_brzycki_1rm(100.0, -5)}")
    except Exception as e:
        print(f"Error with negative reps: {e}")

if __name__ == "__main__":
    asyncio.run(reproduce())
