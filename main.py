from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, select
from starlette.status import HTTP_401_UNAUTHORIZED
from contextlib import asynccontextmanager
import secrets

# --- USERS & AUTH ---
security = HTTPBasic()

USERS = {
    "admin": {"password": "supersecret", "role": "admin"},
    "john": {"password": "readonly123", "role": "viewer"},
    "sarah": {"password": "readpass", "role": "viewer"}
}

def get_current_user(credentials: HTTPBasicCredentials = Depends(security)):
    user = USERS.get(credentials.username)
    if not user or not secrets.compare_digest(user["password"], credentials.password):
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return {"username": credentials.username, "role": user["role"]}

# --- DATABASE SETUP ---
DATABASE_URL = "sqlite+aiosqlite:///./test.db"

engine = create_async_engine(DATABASE_URL, echo=True)
Base = declarative_base()

class Person(Base):
    __tablename__ = "persons"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    points = Column(Integer, default=0)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

SessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# --- LIFESPAN ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

# --- APP START ---
app = FastAPI(lifespan=lifespan)

@app.get("/", response_class=HTMLResponse)
async def dashboard(user=Depends(get_current_user)):
    is_admin = user["role"] == "admin"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Points Dashboard</title>
        <style>
            body {{
                font-family: Arial;
                margin: 40px;
            }}
            input, button {{
                margin: 5px;
                padding: 5px;
            }}
        </style>
    </head>
    <body>
        <h2>Welcome, {user["username"]} ({user["role"]})</h2>

        <h3>Points:</h3>
        <ul id="personList"></ul>

        {"<h3>Add Person:</h3>" if is_admin else ""}
        {"<input type='text' id='newName' placeholder='Name'>" if is_admin else ""}
        {"<button onclick='addPerson()'>Add</button>" if is_admin else ""}

        {"<h3>Update Points:</h3>" if is_admin else ""}
        {"<input type='text' id='updateName' placeholder='Name'>" if is_admin else ""}
        {"<input type='number' id='newPoints' placeholder='Points'>" if is_admin else ""}
        {"<button onclick='updatePoints()'>Update</button>" if is_admin else ""}

        <script>
            const authHeader = "Basic " + btoa("{user['username']}:{USERS[user['username']]['password']}");

            async function loadPeople() {{
                const res = await fetch("/persons", {{
                    headers: {{ Authorization: authHeader }}
                }});
                const data = await res.json();
                const list = document.getElementById("personList");
                list.innerHTML = "";
                data.forEach(p => {{
                    const li = document.createElement("li");
                    li.textContent = `${{p.name}} - ${{p.points}} points`;
                    list.appendChild(li);
                }});
            }}

            {"async function addPerson() {" if is_admin else ""}
            {"  const name = document.getElementById('newName').value;" if is_admin else ""}
            {"  await fetch('/add_person', {" if is_admin else ""}
            {"    method: 'POST'," if is_admin else ""}
            {"    headers: { 'Content-Type': 'application/json', Authorization: authHeader }," if is_admin else ""}
            {"    body: JSON.stringify({ name })" if is_admin else ""}
            {"  });" if is_admin else ""}
            {"  loadPeople();" if is_admin else ""}
            {"}" if is_admin else ""}

            {"async function updatePoints() {" if is_admin else ""}
            {"  const name = document.getElementById('updateName').value;" if is_admin else ""}
            {"  const points = parseInt(document.getElementById('newPoints').value);" if is_admin else ""}
            {"  await fetch('/update_points', {" if is_admin else ""}
            {"    method: 'POST'," if is_admin else ""}
            {"    headers: { 'Content-Type': 'application/json', Authorization: authHeader }," if is_admin else ""}
            {"    body: JSON.stringify({ name, points })" if is_admin else ""}
            {"  });" if is_admin else ""}
            {"  loadPeople();" if is_admin else ""}
            {"}" if is_admin else ""}

            loadPeople();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/persons")
async def get_persons(user=Depends(get_current_user)):
    async with SessionLocal() as session:
        result = await session.execute(select(Person))
        people = result.scalars().all()
        return [{"name": p.name, "points": p.points} for p in people]

@app.post("/add_person")
async def add_person(request: Request, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admins only")
    data = await request.json()
    name = data.get("name")
    async with SessionLocal() as session:
        new_person = Person(name=name, points=0)
        session.add(new_person)
        try:
            await session.commit()
            return {"name": new_person.name, "points": new_person.points}
        except:
            await session.rollback()
            raise HTTPException(status_code=400, detail="Person already exists")

@app.post("/update_points")
async def update_points(request: Request, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admins only")
    data = await request.json()
    name = data.get("name")
    points = data.get("points")
    async with SessionLocal() as session:
        result = await session.execute(select(Person).where(Person.name == name))
        person = result.scalar_one_or_none()
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")
        person.points = points
        await session.commit()
        return {"name": person.name, "points": person.points}
