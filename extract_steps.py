#!/usr/bin/env python3
"""
Complete refactoring: Extract all step logic, create step modules, refactor main.py.
"""
import re
import os

app_dir = r"C:\Users\juhok\Documents\Opinnot\SYKSY2025\Tekoälykurssi\TekoAlyLopputyo\app"
main_file = os.path.join(app_dir, "main.py")
steps_dir = os.path.join(app_dir, "steps")

# Read original main.py
with open(main_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Extract step 4 expander block
step4_match = re.search(r"with st\.expander\('Step 4 — Measurements'.*?\n(?=with st\.expander\('Step 5)", content, re.DOTALL)
step4_code = step4_match.group(0) if step4_match else ""

# Extract step 5 expander block  
step5_match = re.search(r"with st\.expander\('Step 5 — Phase checks'.*?\n(?=with st\.expander\('Step 6)", content, re.DOTALL)
step5_code = step5_match.group(0) if step5_match else ""

# Extract step 6 expander block
step6_match = re.search(r"with st\.expander\('Step 6 — Analysis.*?\n(?=with st\.expander\('Step 7)", content, re.DOTALL)
step6_code = step6_match.group(0) if step6_match else ""

# Extract step 7 expander block
step7_match = re.search(r"with st\.expander\('Step 7 — Switch Setup'.*?\n(?=if st\.button\('Restart'\))", content, re.DOTALL)
step7_code = step7_match.group(0) if step7_match else ""

print(f"Step 4: {len(step4_code)} chars")
print(f"Step 5: {len(step5_code)} chars")
print(f"Step 6: {len(step6_code)} chars")
print(f"Step 7: {len(step7_code)} chars")

# Save extracted code for inspection
with open(os.path.join(app_dir, "extracted_steps.txt"), 'w', encoding='utf-8') as f:
    f.write(f"=== STEP 4 ===\n{step4_code}\n\n")
    f.write(f"=== STEP 5 ===\n{step5_code}\n\n")
    f.write(f"=== STEP 6 ===\n{step6_code}\n\n")
    f.write(f"=== STEP 7 ===\n{step7_code}\n\n")

print("\nExtracted steps saved to extracted_steps.txt")
