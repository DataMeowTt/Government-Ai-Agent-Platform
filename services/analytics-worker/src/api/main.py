import uuid
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from src.pipelines.batch import run_all_analytics
from src.core.logger import logger

app = FastAPI(title="Analytics Worker API", version="1.0.0")

tasks = {}

class TaskResponse(BaseModel):
    task_id: str
    status: str

def run_all_analytics_with_callback(task_id: str):
    try:
        result = run_all_analytics()
        tasks[task_id] = f"done: {result}"
    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}")
        tasks[task_id] = f"failed: {str(e)}"

@app.post("/analytics/run-all", response_model=TaskResponse)
async def start_batch(background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    tasks[task_id] = "running"
    
    background_tasks.add_task(run_all_analytics_with_callback, task_id)
    
    logger.info(f"Started batch task with ID: {task_id}")
    return TaskResponse(task_id=task_id, status="Task submitted successfully.")

@app.get("/analytics/task/{task_id}", response_model=TaskResponse)
def get_status(task_id: str):
    status = tasks.get(task_id, "not_found")
    return TaskResponse(task_id=task_id, status=status)
