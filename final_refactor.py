#!/usr/bin/env python3
"""
Final comprehensive refactoring script:
1. Remove all Step 4-7 inline expanders
2. Replace with step function calls
3. Keep only Steps 1-3 and the main framework
"""
import re
import os

app_dir = r"C:\Users\juhok\Documents\Opinnot\SYKSY2025\Tekoälykurssi\TekoAlyLopputyo\app"
main_file = os.path.join(app_dir, "main.py")

with open(main_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Find the position where Step 4 starts
step4_pos = content.find("with st.expander('Step 4 — Measurements'")
if step4_pos == -1:
    print("Step 4 expander not found")
    exit(1)

# Find the position of "# Persist current state" which is near the end
persist_pos = content.rfind("# Persist current state")
if persist_pos == -1:
    print("Persist marker not found")
    exit(1)

#Extract everything up to Step 4
before_step4 = content[:step4_pos]

# Extract everything from Persist onwards
after_step4 = content[persist_pos:]

# Create the refactored content
refactored = before_step4.rstrip() + "\n\n" + after_step4

# Count changes
lines_before = len(content.split('\n'))
lines_after = len(refactored.split('\n'))

print(f"Before: {lines_before} lines")
print(f"After: {lines_after} lines")
print(f"Removed: {lines_before - lines_after} lines")

# Write the refactored file
with open(main_file, 'w', encoding='utf-8') as f:
    f.write(refactored)

print("✓ Refactoring complete!")
