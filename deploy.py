import logging
import os
import shutil
import subprocess
from datetime import datetime

# Setup Logging
logging.basicConfig(filename='deployment.log', level=logging.INFO, format='%(asctime)s:%(levelname)s:%(message)s')

def backup_artifacts(destination_path):
    """Backs up the deployment artifacts."""
    backup_path = f"{destination_path}_backup_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    try:
        if os.path.exists(destination_path):
            shutil.move(destination_path, backup_path)
            logging.info(f"Backup created at: {backup_path}")
            return backup_path
    except Exception as e:
        logging.error(f"Error creating backup: {e}")
        return None

def branch_exists(git_url, branch, github_token):
    """Checks if the specified branch exists in the remote repository."""
    auth_git_url = git_url.replace("https://", f"https://{github_token}@")
    try:
        output = subprocess.check_output(["git", "ls-remote", "--heads", auth_git_url, branch])
        return bool(output)
    except subprocess.CalledProcessError:
        return False

def get_current_branch(destination_path):
    """Returns the current branch name of the repository at the given destination path."""
    try:
        os.chdir(destination_path)  # Change to the destination directory
        branch_name = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).decode('utf-8').strip()
        return branch_name
    except subprocess.CalledProcessError as e:
        logging.error(f"Error retrieving the current branch name: {e}")
        return None

def clone_repo(git_url, destination_path, branch, github_token):
    """Clones the given GitHub repository into the specified destination path and checks out the specified branch."""
    auth_git_url = git_url.replace("https://", f"https://{github_token}@")
    if branch_exists(git_url, branch, github_token):
        if not os.path.exists(destination_path):
            os.makedirs(destination_path)
        command = ["git", "clone", "-b", branch, auth_git_url, destination_path]
        try:
            subprocess.run(command, check=True)
            logging.info(f"Repository cloned successfully into {destination_path} on branch '{branch}'.")
        except subprocess.CalledProcessError as e:
            logging.error(f"Error cloning repository: {e}")
    else:
        logging.error(f"Error: The branch '{branch}' does not exist in the remote repository.")

def update_repo(git_url, destination_path, branch, github_token):
    """Updates the repository at the destination path."""
    current_branch = get_current_branch(destination_path)
    auth_git_url = git_url.replace("https://", f"https://{github_token}@")
    if current_branch == branch:
        try:
            subprocess.run(["git", "pull", "origin", branch], check=True)
            logging.info(f"Updated the repository in {destination_path} to the latest version of branch '{branch}'.")
        except subprocess.CalledProcessError as e:
            logging.error(f"Error updating repository: {e}")
    else:
        clone_repo(git_url, destination_path, branch, github_token)

def deploy_repo():
    git_url = input("Enter the GitHub repository URL: ").strip()
    destination_path = input("Enter the destination path for the repository: ").strip()
    branch = input("Enter the branch name to deploy (default is 'master'): ").strip() or "master"
    github_token = input("Enter your GitHub Personal Access Token: ").strip()

    if os.path.exists(destination_path) and os.path.exists(os.path.join(destination_path, '.git')):
        # Backup current deployment before making any changes
        backup_path = backup_artifacts(destination_path)
        if backup_path:
            update_repo(git_url, destination_path, branch, github_token)
            logging.info(f"Deployment updated successfully for repository {git_url} on branch {branch}. Backup created at {backup_path}.")
        else:
            logging.error("Backup failed. Deployment aborted.")
    else:
        clone_repo(git_url, destination_path, branch, github_token)
        logging.info(f"Repository {git_url} cloned successfully into {destination_path} on branch '{branch}'.")

if __name__ == "__main__":
    deploy_repo()
