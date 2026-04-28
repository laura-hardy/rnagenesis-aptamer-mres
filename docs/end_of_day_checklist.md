```md
# End-of-Day Coding Checklist

This checklist is designed to balance:
- reproducibility
- good research practice
- minimal overhead

---

## 🖥️ H200 Server (when in use)

### Compute & GPU
- Check GPU usage:
  ```bash
  nvidia-smi
```

- Stop any running jobs you started
- Ensure no idle processes are holding GPU memory

---

### Storage & Files

- Check disk usage:
  ```bash
  du -sh ~
  ```
- Delete unnecessary files:
  - temporary outputs
  - failed runs
  - duplicate checkpoints
- Keep only essential outputs (e.g. final results)

---

### Cleanup

- Remove notebook checkpoints:
  ```bash
  find . -name ".ipynb_checkpoints" -type d -exec rm -rf {} + 2>/dev/null
  ```
- Optional: compress large outputs if needed:
  ```bash
  tar -czf archive_name.tar.gz folder_name/
  ```

---

### Reproducibility

- If environment changed:
  ```bash
  conda env export --no-builds > environment/h200_environment.yml
  pip freeze > environment/h200_pip_freeze.txt
  ```
- Note any important changes in `docs/log.md`

---

## 💻 Mac (Cursor / Terminal)

### Git hygiene

- Check status:
  ```bash
  git status
  ```
- Commit changes:
  ```bash
  git add .
  git commit -m "Short descriptive message"
  git push
  ```

To finish up on the mac:

```
conda deactivate
exit
```

## Then close the Terminal window.

### Logging

- Add a short entry to `docs/log.md`:
  - what you did
  - current state
  - next step

Example:

```md
## YYYY-MM-DD — End of session

- Completed X
- Encountered Y
- Next: Z
```

---

### Code state

- Leave a clear next step in code or log:
  - `# TODO:` or `# NEXT:`
- Remove unnecessary debug prints if obvious

---

## 🔁 Universal (always)

### Quick sanity checks

- No large unintended files added to repo
- No sensitive data committed
- Work is pushed to GitHub

---

### Minimal “where I left off”

Write 1–3 lines:

- what is working
- what is broken
- what to do next

---

## ⚡ Optional helper

You can run:

```bash
du -sh ~
git status
```

to quickly check:

- disk usage
- repo state

---

## 🧠 Principle

> Aim for consistency, not perfection.

A simple, repeatable workflow is more valuable than a complex one you don’t follow.

```

```

