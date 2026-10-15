"""Study Agent — study planner, quiz, learning progress"""
class StudyAgent:
    async def create_plan(self, user_id: str, subject: str, exam_date=None):
        raise NotImplementedError
