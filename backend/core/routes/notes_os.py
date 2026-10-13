"""
Sanaa OS — Notes & Todo Persistence
Lightweight JSON-backed storage for personal productivity data.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from core.routes import deps

router = APIRouter()

DATA_DIR = "/var/www/ai.sanaa.co/data/os"
NOTES_FILE = os.path.join(DATA_DIR, "notes.json")
TODOS_FILE = os.path.join(DATA_DIR, "todos.json")
FOLDERS_FILE = os.path.join(DATA_DIR, "note_folders.json")

os.makedirs(DATA_DIR, exist_ok=True)


def _load_json(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_json(path: str, data: list):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    os.replace(tmp, path)


def _load_folder_registry() -> dict:
    if not os.path.exists(FOLDERS_FILE):
        return {}
    try:
        with open(FOLDERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_folder_registry(data: dict):
    tmp = FOLDERS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, FOLDERS_FILE)


def _folders_for_user(email: str) -> list[str]:
    notes = _load_json(NOTES_FILE)
    from_notes = {(n.get("folder") or "General") for n in notes if n.get("owner") == email}
    registry = _load_folder_registry().get(email, [])
    folders = sorted(from_notes | set(registry))
    if "General" not in folders:
        folders.insert(0, "General")
    return folders


# ============================================
# Notes
# ============================================
class NoteCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(default="", max_length=50000)
    folder: str = Field(default="General", max_length=100)
    color: Optional[str] = Field(default=None)
    pinned: bool = Field(default=False)


class NoteUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    content: Optional[str] = Field(default=None, max_length=50000)
    folder: Optional[str] = Field(default=None, max_length=100)
    color: Optional[str] = Field(default=None)
    pinned: Optional[bool] = Field(default=None)


@router.get("/api/notes")
async def list_notes(folder: Optional[str] = None, user: dict = Depends(deps.require_auth)):
    notes = _load_json(NOTES_FILE)
    email = user["email"]
    user_notes = [n for n in notes if n.get("owner") == email]
    if folder:
        user_notes = [n for n in user_notes if n.get("folder") == folder]
    user_notes.sort(key=lambda n: (not n.get("pinned", False), n.get("updated_at", "")), reverse=True)
    return {"notes": user_notes}


@router.post("/api/notes")
async def create_note(body: NoteCreate, user: dict = Depends(deps.require_auth)):
    notes = _load_json(NOTES_FILE)
    now = datetime.now(timezone.utc).isoformat()
    note = {
        "id": str(uuid.uuid4())[:8],
        "owner": user["email"],
        "title": body.title,
        "content": body.content,
        "folder": body.folder,
        "color": body.color,
        "pinned": body.pinned,
        "created_at": now,
        "updated_at": now,
    }
    notes.append(note)
    _save_json(NOTES_FILE, notes)
    return note


@router.get("/api/notes/folders/list")
async def list_note_folders(user: dict = Depends(deps.require_auth)):
    return {"folders": _folders_for_user(user["email"])}


class FolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class FolderRename(BaseModel):
    old_name: str = Field(..., min_length=1, max_length=100)
    new_name: str = Field(..., min_length=1, max_length=100)


@router.post("/api/notes/folders")
async def create_note_folder(body: FolderCreate, user: dict = Depends(deps.require_auth)):
    name = body.name.strip()
    if not name or name == "General":
        raise HTTPException(400, "Invalid folder name")
    registry = _load_folder_registry()
    email = user["email"]
    user_folders = set(registry.get(email, []))
    if name in _folders_for_user(email):
        return {"folder": name, "created": False}
    user_folders.add(name)
    registry[email] = sorted(user_folders)
    _save_folder_registry(registry)
    return {"folder": name, "created": True}


@router.put("/api/notes/folders/rename")
async def rename_note_folder(body: FolderRename, user: dict = Depends(deps.require_auth)):
    old_name = body.old_name.strip()
    new_name = body.new_name.strip()
    if not old_name or not new_name or old_name == "General":
        raise HTTPException(400, "Cannot rename this folder")
    if old_name == new_name:
        return {"old_name": old_name, "new_name": new_name, "updated": 0}

    notes = _load_json(NOTES_FILE)
    email = user["email"]
    updated = 0
    for note in notes:
        if note.get("owner") == email and (note.get("folder") or "General") == old_name:
            note["folder"] = new_name
            note["updated_at"] = datetime.now(timezone.utc).isoformat()
            updated += 1
    if updated:
        _save_json(NOTES_FILE, notes)

    registry = _load_folder_registry()
    user_folders = [f for f in registry.get(email, []) if f != old_name]
    if new_name not in user_folders:
        user_folders.append(new_name)
    registry[email] = sorted(user_folders)
    _save_folder_registry(registry)

    return {"old_name": old_name, "new_name": new_name, "updated": updated}


@router.get("/api/notes/{note_id}")
async def get_note(note_id: str, user: dict = Depends(deps.require_auth)):
    notes = _load_json(NOTES_FILE)
    note = next((n for n in notes if n.get("id") == note_id and n.get("owner") == user["email"]), None)
    if not note:
        raise HTTPException(404, "Note not found")
    return note


@router.put("/api/notes/{note_id}")
async def update_note(note_id: str, body: NoteUpdate, user: dict = Depends(deps.require_auth)):
    notes = _load_json(NOTES_FILE)
    for note in notes:
        if note.get("id") == note_id and note.get("owner") == user["email"]:
            if body.title is not None:
                note["title"] = body.title
            if body.content is not None:
                note["content"] = body.content
            if body.folder is not None:
                note["folder"] = body.folder
            if body.color is not None:
                note["color"] = body.color
            if body.pinned is not None:
                note["pinned"] = body.pinned
            note["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_json(NOTES_FILE, notes)
            return note
    raise HTTPException(404, "Note not found")


@router.delete("/api/notes/{note_id}")
async def delete_note(note_id: str, user: dict = Depends(deps.require_auth)):
    notes = _load_json(NOTES_FILE)
    filtered = [n for n in notes if not (n.get("id") == note_id and n.get("owner") == user["email"])]
    if len(filtered) == len(notes):
        raise HTTPException(404, "Note not found")
    _save_json(NOTES_FILE, filtered)
    return {"deleted": True}


# ============================================
# Todos (Reminders-style lists)
# ============================================
class TodoCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    text: str = Field(..., min_length=1, max_length=500)
    priority: str = Field(default="medium")
    due_date: Optional[str] = Field(default=None)
    tags: List[str] = Field(default_factory=list)
    list_name: str = Field(default="Personal", max_length=100, alias="list")


class TodoUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    text: Optional[str] = Field(default=None, max_length=500)
    done: Optional[bool] = Field(default=None)
    priority: Optional[str] = Field(default=None)
    due_date: Optional[str] = Field(default=None)
    tags: Optional[List[str]] = Field(default=None)
    list_name: Optional[str] = Field(default=None, max_length=100, alias="list")


@router.get("/api/todos")
async def list_todos(
    status: Optional[str] = None,
    list_name: Optional[str] = Query(None, alias="list"),
    user: dict = Depends(deps.require_auth),
):
    todos = _load_json(TODOS_FILE)
    email = user["email"]
    user_todos = [t for t in todos if t.get("owner") == email]
    if status == "active":
        user_todos = [t for t in user_todos if not t.get("done", False)]
    elif status == "completed":
        user_todos = [t for t in user_todos if t.get("done", False)]
    if list_name:
        user_todos = [t for t in user_todos if (t.get("list") or "Personal") == list_name]
    user_todos.sort(key=lambda t: (t.get("done", False), t.get("due_date") or "9999", t.get("created_at", "")))
    return {"todos": user_todos}


@router.get("/api/todos/lists")
async def list_todo_lists(user: dict = Depends(deps.require_auth)):
    todos = _load_json(TODOS_FILE)
    lists = sorted({(t.get("list") or "Personal") for t in todos if t.get("owner") == user["email"]})
    if "Personal" not in lists:
        lists.insert(0, "Personal")
    return {"lists": lists}


@router.post("/api/todos")
async def create_todo(body: TodoCreate, user: dict = Depends(deps.require_auth)):
    todos = _load_json(TODOS_FILE)
    now = datetime.now(timezone.utc).isoformat()
    todo = {
        "id": str(uuid.uuid4())[:8],
        "owner": user["email"],
        "text": body.text,
        "done": False,
        "priority": body.priority,
        "due_date": body.due_date,
        "tags": body.tags,
        "list": body.list_name,
        "created_at": now,
        "updated_at": now,
    }
    todos.append(todo)
    _save_json(TODOS_FILE, todos)
    return todo


@router.put("/api/todos/{todo_id}")
async def update_todo(todo_id: str, body: TodoUpdate, user: dict = Depends(deps.require_auth)):
    todos = _load_json(TODOS_FILE)
    for todo in todos:
        if todo.get("id") == todo_id and todo.get("owner") == user["email"]:
            if body.text is not None:
                todo["text"] = body.text
            if body.done is not None:
                todo["done"] = body.done
            if body.priority is not None:
                todo["priority"] = body.priority
            if body.due_date is not None:
                todo["due_date"] = body.due_date
            if body.tags is not None:
                todo["tags"] = body.tags
            if body.list_name is not None:
                todo["list"] = body.list_name
            todo["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_json(TODOS_FILE, todos)
            return todo
    raise HTTPException(404, "Todo not found")


@router.delete("/api/todos/{todo_id}")
async def delete_todo(todo_id: str, user: dict = Depends(deps.require_auth)):
    todos = _load_json(TODOS_FILE)
    filtered = [t for t in todos if not (t.get("id") == todo_id and t.get("owner") == user["email"])]
    if len(filtered) == len(todos):
        raise HTTPException(404, "Todo not found")
    _save_json(TODOS_FILE, filtered)
    return {"deleted": True}
