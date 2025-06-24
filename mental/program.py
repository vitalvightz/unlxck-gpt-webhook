from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List

@dataclass
class MentalActivity:
    name: str
    duration_minutes: int
    description: str

@dataclass
class DailyPlan:
    day: date
    activities: List[MentalActivity] = field(default_factory=list)

def default_program() -> List[MentalActivity]:
    """Return a basic list of mental training activities."""
    return [
        MentalActivity("Mindfulness Meditation", 10, "Sit quietly and focus on breathing"),
        MentalActivity("Goal Visualization", 5, "Visualize your main objectives for the day"),
        MentalActivity("Journaling", 10, "Write down thoughts and reflections"),
    ]

def create_week_plan(start: date) -> List[DailyPlan]:
    """Generate a week-long plan starting from the given date."""
    plan = []
    for i in range(7):
        day_date = start + timedelta(days=i)
        plan.append(DailyPlan(day_date, default_program()))
    return plan

if __name__ == "__main__":
    week = create_week_plan(date.today())
    for day_plan in week:
        print(day_plan.day.strftime("%A %Y-%m-%d"))
        for act in day_plan.activities:
            print(f"  - {act.name} ({act.duration_minutes} min): {act.description}")
        print()
