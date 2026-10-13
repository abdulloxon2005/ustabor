from fastapi import FastAPI

app = FastAPI (
    title = "Task manager API",
    description = "Vazifalarni boshqarish API",
    version = "1.0.0",
)

@app.get("/")
def home():
    return {"message":"Task manager API ishlamoqda"}

