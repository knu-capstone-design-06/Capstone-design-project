"""Judgment layer: rule table + Jev, run in the backend (decision 2026-11-04).

Every window the frontend sends (/features) gives the rule table one input line; the
table opens, keeps, replaces or withdraws one support per session, and in shadow mode Jev
is asked about the state and the proposal and only the record is kept. The screen still
follows the placeholder result until thresholds are agreed (docs/Jev-Integration.md).
"""
