<!-- AIStudio Global Agent Instructions -->

# AIStudio - Global AI Agent Instructions

## Project Vision

AIStudio is a local-first AI-powered Manhwa, Manga and Manhua platform.

The final goal is to build the best self-hosted reader available.

Core features:

- Library Management
- Reader
- Search
- OCR
- AI Summaries
- Character Tracking
- Timeline Tracking
- World Memory
- Recommendations
- Offline First
- Local AI
- NAS Support
- Windows Support
- Mobile Support
- Web Support
- Multi-user Support

---

# Development Philosophy

Build a WORKING product first.

Do NOT over-engineer.

Always prefer:

Working code
>
Clean code
>
Perfect architecture

Every change should move the application closer to a usable product.

---

# Architecture Rules

Never duplicate code.

Reuse existing services whenever possible.

Reuse existing components.

Separate:

- UI
- Business Logic
- Database
- API
- AI

Never tightly couple unrelated modules.

Prefer modular services.

Keep files organized.

---

# Coding Standards

Write production-ready code.

Use strict TypeScript.

Use meaningful names.

Use reusable components.

Write proper error handling.

Validate inputs.

Avoid unnecessary dependencies.

Never leave placeholder implementations.

Never leave TODO comments.

Never fake implementations.

If something cannot be implemented, explain why.

---

# Frontend Rules

Use:

- Next.js App Router
- TypeScript
- Tailwind
- Zustand

Requirements:

Responsive

Fast

Dark mode friendly

Keyboard friendly

Lazy loading

Virtualization when useful

Avoid unnecessary re-renders.

---

# Backend Rules

Use:

FastAPI

SQLite for MVP

Design for PostgreSQL migration.

Separate:

Routes

Services

Database

Models

Utilities

Background workers

Never place business logic inside routes.

---

# Database Rules

Normalize data.

Never duplicate information.

Use foreign keys.

Track:

Library

Series

Chapters

Pages

Collections

Tags

Categories

Reading Progress

Import History

AI Metadata

Downloads

---

# AI Rules

Everything must work locally.

Prefer Ollama.

Support multiple models.

Never require cloud APIs unless explicitly requested.

AI should improve user experience rather than replace normal functionality.

---

# Windows Rules

This project targets Windows first.

Always use PowerShell-compatible syntax.

Never assume Linux.

Never assume macOS.

Never use:

open

xdg-open

&&

||

Run commands separately.

Correct:

npm run build

npm run lint

npm run typecheck

Incorrect:

npm run build && npm run lint

---

# Command Execution Rules

Always execute commands individually.

If a command fails:

Read the error.

Fix the issue.

Run the command again.

Do not continue until the command succeeds or clearly explain why it cannot.

---

# Before Writing Code

Always:

Read the relevant files.

Understand the current implementation.

Reuse existing code when possible.

Avoid rewriting working functionality.

---

# Before Declaring Completion

A task is NOT complete until ALL of these pass.

Verification Pass 1

Read every modified file.

Check:

Logic

Imports

Exports

Types

Unused code

Dead code

Duplicate code

Fix everything.

---

Verification Pass 2

Verify every requirement from the original task.

Create a checklist.

Every requirement must be:

PASS

or

FAIL

If anything is FAIL:

Continue working.

---

Verification Pass 3

Run every applicable command separately.

npm run build

npm run lint

npm run typecheck

Run tests if available.

Fix every realistic error.

Run the commands again.

---

Verification Pass 4

Read every changed file one final time.

Verify:

No placeholders

No TODOs

No mock implementations

No dead code

No broken imports

No obvious bugs

No incomplete features

---

# Definition of Done

A feature is only complete if:

✓ Builds successfully

✓ Type checks successfully

✓ Lint passes

✓ No placeholder code

✓ No TODO comments

✓ No fake implementations

✓ Integrated into the application

✓ Existing functionality still works

✓ Requirements satisfied

Never claim "Completed" until every Definition of Done item passes.

---

# Reporting

When finished, provide:

Files created

Files modified

Features implemented

Database changes

API changes

Remaining work

Known limitations

Verification results

Build status

Lint status

Type-check status

Never exaggerate what has been implemented.