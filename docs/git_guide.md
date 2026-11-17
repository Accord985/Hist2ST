# Git for the Hist2ST Team: A Beginner's Guide

This guide assumes you have never used Git. It covers getting a project onto your computer, saving work, undoing mistakes, and collaborating through branches and pull requests. Commands work in PowerShell, Windows Terminal, Git Bash, macOS Terminal, and most Linux terminals unless noted.

The companion lecture PDF, `w4_data-explore_exp-design_git_latex_cluster.pdf`, is the course reference for Git and team workflow. This guide applies those ideas to this repository and its team conventions in [notes.md](notes.md): keep `main` runnable, make one branch per task, commit small changes, and have a teammate review before merging.

## 1. What Git does

Git is a version control system. It records snapshots of files so you can see what changed, save useful checkpoints, and combine work from multiple people. Git runs on your computer. A hosting service such as GitHub or GitLab stores a shared copy online and provides pull requests.

A few terms:

- **Repository (repo):** the project and its Git history.
- **Commit:** a named snapshot of selected changes, with a message explaining them.
- **Remote:** another copy of the repository, usually on GitHub or GitLab. The common remote name is `origin`.
- **Branch:** a movable line of work. The shared stable branch is often called `main`.
- **Pull request (PR):** a request to review and merge a branch into another branch. GitLab often calls this a **merge request (MR)**.

Git does not automatically save every edit. You choose which changes to include in each commit.

## 2. Install Git and identify yourself

Install Git from [git-scm.com](https://git-scm.com/downloads) if `git --version` does not print a version in your terminal. On Windows, Git Bash is included and PowerShell works too.

Set the name and email that should appear on your commits. Use the email associated with your Git hosting account if you want commits linked to your profile:

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

Check the settings:

```bash
git config --global --list
```

These settings identify your commits; they are not your account password.

## 3. Connect to the project: HTTPS or SSH

The project owner should give you the repository URL and access. A URL generally looks like one of these:

```text
https://github.com/organization/project.git
git@github.com:organization/project.git
```

HTTPS is straightforward and may prompt you to sign in through a browser or credential manager. Hosting providers generally require a browser login or personal access token rather than your account password for Git over HTTPS.

SSH uses a key pair on your computer: a **private key** that stays on your computer, and a **public key** that you add to your Git hosting account. SSH is convenient for repeated use. Never send anyone your private key.

### Set up an SSH key

First check whether you already have a key. On Windows, run this in PowerShell or Git Bash; on macOS/Linux, use Terminal:

```bash
ls ~/.ssh
```

If you see a key such as `id_ed25519` and its matching `id_ed25519.pub`, you may use that pair. Do not overwrite a key you already rely on. Otherwise create one (replace the example email):

```bash
ssh-keygen -t ed25519 -C "you@example.com"
```

Press Enter to accept the default file location. Add a passphrase when prompted for extra protection. The private key is `~/.ssh/id_ed25519`; the public key is `~/.ssh/id_ed25519.pub`.

Display the public key and copy the entire line:

```bash
cat ~/.ssh/id_ed25519.pub
```

In your Git hosting account settings, find **SSH keys** (often under **SSH and GPG keys**) and add that public key. Only upload the `.pub` key. If your key has a passphrase, an SSH agent can remember it for your login session; setup differs by operating system.

For GitHub, check the connection with:

```bash
ssh -T git@github.com
```

For another host, use its documented SSH test command. The first connection may ask whether you trust the host fingerprint. Verify it using your hosting provider's official documentation before accepting it.

## 4. Clone the project

**Clone** means download the repository and its history to your computer. Choose the URL for the access method you configured:

```bash
git clone git@github.com:organization/project.git
```

or:

```bash
git clone https://github.com/organization/project.git
```

Replace the example URL with the one the team gave you. Git creates a project folder. Move into it:

```bash
cd project
```

Check your location and the repository status:

```bash
pwd
git status
```

If the project is already on your computer, do not clone it again; open a terminal in that project folder.

## 5. The everyday workflow

A typical individual workflow is:

1. Get the latest shared changes.
2. Create a branch for one task.
3. Edit and inspect your changes.
4. Stage the changes you want in the next checkpoint.
5. Commit them with a clear message.
6. Push the branch to the remote when you want a backup or review.

### Start a task branch

Start from an up-to-date `main` branch:

```bash
git switch main
git pull origin main
git switch -c docs/git-guide
```

`git switch -c` creates and switches to a branch. Use a short name that says what the task is, such as `fix/patch-loading` or `experiment/ridge-baseline`. Keep one task per branch. This keeps review focused and makes it easier to combine work.

### Edit and inspect

Edit files using your normal editor. Then ask Git what changed:

```bash
git status
git diff
```

`git status` summarizes changed, staged, and untracked files. `git diff` shows edits that have not been staged. Review these before committing. In this project, do not commit large data files or model weights unless the team has agreed; never commit passwords, API keys, restricted data, or patient data. Check `.gitignore` and ask a teammate if you are unsure whether a file belongs in Git.

### Stage and commit

Staging selects the changes for the next commit. Stage a specific file:

```bash
git add docs/my-notes.md
```

Or stage all current changes (review `git status` first):

```bash
git add .
```

Check what is staged, then commit:

```bash
git diff --staged
git commit -m "Add onboarding notes for Git"
```

A good commit message briefly says what the commit changes. Make small, understandable commits rather than one giant commit at the end. Your files remain on disk after committing; the commit adds a checkpoint to the history.

### Push your branch

The first time you push a new branch, use:

```bash
git push -u origin docs/git-guide
```

The `-u` connects your local branch to its remote counterpart, so later you can usually run:

```bash
git push
```

Pushing uploads commits on your branch. It does not merge them into `main`.

## 6. Undo or recover from mistakes

First inspect the state before undoing anything:

```bash
git status
git diff
git log --oneline --decorate -8
```

The safest command depends on whether the change is unstaged, staged, or committed.

### Discard an unstaged edit to one file

This replaces the working copy of the file with its last committed version, so the edit is lost:

```bash
git restore path/to/file
```

Use this only if you are sure you no longer need those edits. If unsure, copy the file or save the changes elsewhere first.

### Unstage a file but keep its edits

If you staged the wrong file, remove it from the staging area without discarding the edits:

```bash
git restore --staged path/to/file
```

### Undo a commit that has not been shared

To undo the most recent commit but keep its changes staged for editing or recommitting:

```bash
git reset --soft HEAD~1
```

To undo that commit and keep the changes in your files but unstaged:

```bash
git reset HEAD~1
```

Avoid `git reset --hard`: it discards uncommitted work. Avoid rewriting commits that have already been pushed and may be used by teammates. If you are unsure, ask before using reset.

### Undo a commit that has been pushed/shared

Use `git revert` to make a new commit that reverses an earlier commit. This preserves the shared history:

```bash
git log --oneline
git revert <commit-id>
git push
```

Replace `<commit-id>` with the identifier shown by `git log`. Git may open an editor for the revert commit message; save and close it to finish. If conflicts occur, resolve them as described below.

### Recover a deleted or overwritten tracked file

If the file was committed before, restore its last committed contents with:

```bash
git restore path/to/file
```

If you committed a change and later need to find an earlier version, use `git log -- path/to/file`, then inspect a version with `git show <commit-id>:path/to/file`. Ask for help before resetting if you are not sure which history to keep.

## 7. Work as a team with branches and pull requests

A branch lets each person work without changing `main` directly. A PR lets teammates inspect a proposed change, discuss it, and check that it fits with other work. For this project, use one task per branch and merge only after a teammate reviews it. Keep `main` in a working state.

### Contributor steps

1. Update your local `main`:

   ```bash
   git switch main
   git pull origin main
   ```

2. Create a task branch:

   ```bash
   git switch -c feature/short-task-name
   ```

3. Edit, inspect, stage, and commit your work. Push the branch:

   ```bash
   git push -u origin feature/short-task-name
   ```

4. On GitHub/GitLab, open a pull request from your branch into `main`. Describe the purpose, key changes, and how you checked the work. Link related issues or include screenshots/results when useful. Request a teammate as reviewer.

5. Respond to review comments. Make requested edits on the same local branch, commit, then push again. The PR updates automatically.

6. Once approved and required checks pass, merge using the team's chosen merge option. Delete the remote branch after merging if the hosting service offers that option and the team does not need the branch.

### Keep your branch current

While your task is in progress, `main` may change. Incorporate the latest `main` into your branch:

```bash
git switch main
git pull origin main
git switch feature/short-task-name
git merge main
```

If Git reports conflicts, it will mark the affected files. Open each file and choose the correct combined content; remove conflict marker lines (`<<<<<<<`, `=======`, `>>>>>>>`). Then inspect and complete the merge:

```bash
git status
git add path/to/resolved-file
git commit
```

Run the relevant project checks and push the updated branch:

```bash
git push
```

If a conflict is confusing, coordinate with the teammate who changed that file rather than guessing. Do not commit conflict markers.

### After a PR is merged

Update your local `main` and start the next task from it:

```bash
git switch main
git pull origin main
git switch -c feature/next-task
```

## 8. Small command reference

| Goal | Command |
| --- | --- |
| See the current branch and changes | `git status` |
| See unstaged edits | `git diff` |
| See staged edits | `git diff --staged` |
| Show recent commits | `git log --oneline --decorate -8` |
| Download latest changes for current branch | `git pull` |
| Create and enter a branch | `git switch -c branch-name` |
| Change branches | `git switch branch-name` |
| Stage one file | `git add path/to/file` |
| Save a checkpoint | `git commit -m "Describe change"` |
| Upload branch commits | `git push` |

## 9. A few habits that prevent trouble

- Run `git status` often; it tells you where you are and what Git sees.
- Pull the latest `main` before starting a task.
- Use one branch per task and small commits with clear messages.
- Review staged changes before each commit.
- Push regularly so your branch has a remote backup and teammates can review it.
- Keep data, model weights, secrets, restricted files, and patient information out of commits.
- Ask before force-pushing or rewriting shared history. When undoing shared work, prefer `git revert`.
- If you get stuck, save the exact output of `git status` and ask a teammate before running commands that discard changes.
