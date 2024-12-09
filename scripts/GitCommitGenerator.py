import os
import subprocess
import re
from Api_Keys.OpenApi import ApiKey # Replace the import Api key from local

# Optional: AI Integration
def generate_ai_summary(changes):
    import openai
    openai.api_key = ApiKey
    response = openai.Completion.create(
        model="gpt-3.5-turbo",
        prompt=f"Summarize the following code changes:\n{changes}",
        max_tokens=100,
    )
    return response.choices[0].text.strip()

# Analyze Git Diff
def get_git_diff():
    try:
        diff = subprocess.check_output(["git", "diff", "--cached"], text=True)
        return diff
    except subprocess.CalledProcessError as e:
        print("Error fetching git diff:", e)
        return ""

# Generate Commit Message
def generate_commit_message(diff):
    summary = []
    for line in diff.splitlines():
        if line.startswith("diff --git"):
            file_name = re.findall(r" b/(.+)", line)
            if file_name:
                summary.append(f"Modified file: {file_name[0]}")
        elif line.startswith("+") and not line.startswith("+++"):
            summary.append(f"Added: {line[1:]}")
        elif line.startswith("-") and not line.startswith("---"):
            summary.append(f"Removed: {line[1:]}")

    return "\n".join(summary)

def main():
    diff = get_git_diff()
    if not diff:
        print("No changes to commit.")
        return

    # Generate commit message
    commit_summary = generate_commit_message(diff)

    # Optionally, enhance with AI
    ai_summary = generate_ai_summary(diff) if "YOUR_API_KEY" else ""
    final_message = ai_summary or commit_summary

    print("\nGenerated Commit Message:")
    print(final_message)

    # Prompt user for confirmation or editing
    use_commit = input("\nUse this commit message? (y/n): ").lower()
    if use_commit == "y":
        subprocess.call(["git", "commit", "-m", final_message])
    else:
        print("Commit aborted. Please write your own message.")

if __name__ == "__main__":
    main()
