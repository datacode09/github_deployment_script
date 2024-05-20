import logging
import os
import shutil
import subprocess
import argparse
import time
import getpass
from pathlib import Path
import stat

# Setup Logging
logger = logging.getLogger('DeploymentLogger')
logger.setLevel(logging.INFO)
handler = logging.FileHandler('deployment.log')
formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def verify_git_installation():
    """Check if Git is installed."""
    logger.info("Starting verify_git_installation function.")
    try:
        subprocess.check_output(["git", "--version"])
        logger.info("Git is installed.")
    except subprocess.CalledProcessError as e:
        logger.error("Git is not installed. Please install Git to proceed.")
        raise EnvironmentError("Git is not installed. Please install Git to proceed.") from e

def retry_operation(operation, max_retries=3, delay=5):
    """Retries a file operation in case of failure."""
    logger.info("Starting retry_operation function.")
    for attempt in range(max_retries):
        try:
            operation()
            return True
        except Exception as e:
            logger.error(f"Operation failed: {e}. Retrying {attempt + 1}/{max_retries}...")
            time.sleep(delay)
    return False

def read_gitignore(path):
    """Reads the .gitignore file and returns a list of patterns to ignore."""
    logger.info("Starting read_gitignore function.")
    gitignore_path = Path(path) / ".gitignore"
    if gitignore_path.exists():
        with open(gitignore_path, "r") as file:
            return [line.strip() for line in file if line.strip() and not line.startswith("#")]
    return []

def backup_artifacts(destination_path, backup_repo_path, ignore_patterns):
    """Backs up the deployment artifacts according to .gitignore patterns."""
    logger.info("Starting backup_artifacts function.")
    def operation():
        if os.path.exists(backup_repo_path):
            shutil.rmtree(backup_repo_path)  # Remove the existing backup directory
        shutil.copytree(destination_path, backup_repo_path, ignore=shutil.ignore_patterns('.git', '.gitignore', *ignore_patterns))
        logger.info(f"Backup created at: {backup_repo_path}")
        return backup_repo_path

    if retry_operation(operation):
        return backup_repo_path
    else:
        logger.error("Error creating backup after multiple attempts.")
        return None

def restore_backup(backup_repo_path, destination_path):
    """Restores the backup in case of deployment failure."""
    logger.info("Starting restore_backup function.")
    def operation():
        if os.path.exists(destination_path):
            shutil.rmtree(destination_path)
        shutil.copytree(backup_repo_path, destination_path, ignore=shutil.ignore_patterns('.git', '.gitignore'), dirs_exist_ok=True)
        logger.info(f"Backup restored from {backup_repo_path} to {destination_path}")
        print(f"Backup restored from {backup_repo_path} to {destination_path}")

    if not retry_operation(operation):
        logger.error("Error restoring backup after multiple attempts.")
        print("Error restoring backup after multiple attempts.")

def branch_exists(git_url, branch, github_token):
    """Checks if the specified branch exists in the remote repository."""
    logger.info("Starting branch_exists function.")
    auth_git_url = git_url.replace("https://", f"https://{github_token}@")
    try:
        output = subprocess.check_output(["git", "ls-remote", "--heads", auth_git_url, branch])
        return bool(output)
    except subprocess.CalledProcessError as e:
        logger.error(f"Error checking branch existence: {e}")
        return False

def get_current_branch(destination_path):
    """Returns the current branch name of the repository at the given destination path."""
    logger.info("Starting get_current_branch function.")
    try:
        os.chdir(destination_path)  # Change to the destination directory
        branch_name = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).decode('utf-8').strip()
        return branch_name
    except subprocess.CalledProcessError as e:
        logger.error(f"Error retrieving the current branch name: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error occurred while retrieving the current branch name: {e}")
        return None

def make_git_writable_and_remove(git_path):
    """Changes the permissions of the .git directory to writable and removes it."""
    logger.info("Starting make_git_writable_and_remove function.")
    for root, dirs, files in os.walk(git_path):
        for dir in dirs:
            os.chmod(os.path.join(root, dir), stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        for file in files:
            os.chmod(os.path.join(root, file), stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
    shutil.rmtree(git_path)

def clone_repo(git_url, temp_clone_path, branch, github_token):
    """Clones the given GitHub repository into a temporary location."""
    logger.info("Starting clone_repo function.")
    auth_git_url = git_url.replace("https://", f"https://{github_token}@")
    if branch_exists(git_url, branch, github_token):
        if not os.path.exists(temp_clone_path):
            os.makedirs(temp_clone_path)
        command = ["git", "clone", "-b", branch, "--single-branch", auth_git_url, temp_clone_path]
        try:
            subprocess.run(command, check=True)
            logger.info(f"Repository cloned successfully into {temp_clone_path} on branch '{branch}'.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Error cloning repository: subprocess error occurred - {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error occurred while cloning repository: {e}")
            raise
    else:
        logger.error(f"Error: The branch '{branch}' does not exist in the remote repository.")
        raise ValueError(f"The branch '{branch}' does not exist in the remote repository.")

def deploy_repo(git_url, base_destination_path, branch, github_token, backup_base_path):
    logger.info("Starting deploy_repo function.")
    verify_git_installation()

    repo_name = os.path.basename(git_url).replace('.git', '')
    destination_path = os.path.join(base_destination_path, repo_name)
    backup_repo_path = os.path.join(backup_base_path, repo_name)
    temp_clone_path = os.path.join(base_destination_path, f"{repo_name}_temp")
    
    if not os.path.isdir(base_destination_path):
        logger.error("The base destination path is not a valid directory.")
        print("The base destination path is not a valid directory.")
        return

    if not os.path.isdir(backup_base_path):
        logger.error("The base backup path is not a valid directory.")
        print("The base backup path is not a valid directory.")
        return

    ignore_patterns = read_gitignore(destination_path)
    rollback_needed = False

    if os.path.exists(destination_path):
        # Backup current deployment before making any changes
        backup_repo_path = backup_artifacts(destination_path, backup_repo_path, ignore_patterns)
        if backup_repo_path:
            try:
                # Clean the destination path
                if not retry_operation(lambda: shutil.rmtree(destination_path)):
                    logger.error("Failed to clean the destination path after multiple attempts. Deployment aborted.")
                    print("Failed to clean the destination path. Deployment aborted.")
                    return

                os.makedirs(destination_path)
                # Clone the repository to a temporary location
                clone_repo(git_url, temp_clone_path, branch, github_token)
                # Make .git directory writable and remove it in the temporary location
                make_git_writable_and_remove(os.path.join(temp_clone_path, '.git'))
                # Copy the contents from the temporary location to the destination path, excluding .git and .gitignore
                shutil.copytree(temp_clone_path, destination_path, ignore=shutil.ignore_patterns('.git', '.gitignore'), dirs_exist_ok=True)
                # Remove the temporary clone path
                shutil.rmtree(temp_clone_path)
                logger.info(f"Deployment updated successfully for repository {git_url} on branch {branch}. Backup created at {backup_repo_path}.")
                print(f"Deployment updated successfully for repository {git_url} on branch {branch}. Backup created at {backup_repo_path}.")
            except Exception as e:
                logger.error(f"Deployment failed: {e}. Initiating rollback.")
                print("Deployment failed. Initiating rollback.")
                rollback_needed = True
        else:
            logger.error("Backup failed. Deployment aborted.")
            print("Backup failed. Deployment aborted.")
            return
    else:
        try:
            os.makedirs(destination_path)
            # Clone the repository to a temporary location
            clone_repo(git_url, temp_clone_path, branch, github_token)
            # Make .git directory writable and remove it in the temporary location
            make_git_writable_and_remove(os.path.join(temp_clone_path, '.git'))
            # Copy the contents from the temporary location to the destination path, excluding .git and .gitignore
            shutil.copytree(temp_clone_path, destination_path, ignore=shutil.ignore_patterns('.git', '.gitignore'), dirs_exist_ok=True)
            # Remove the temporary clone path
            shutil.rmtree(temp_clone_path)
            logger.info(f"Repository {git_url} cloned successfully into {destination_path} on branch '{branch}'.")
            print(f"Repository {git_url} cloned successfully into {destination_path} on branch '{branch}'")
        except Exception as e:
            logger.error(f"Deployment failed: {e}")
            print("Deployment failed.")
            rollback_needed = True

    if rollback_needed and os.path.exists(backup_repo_path):
        restore_backup(backup_repo_path, destination_path)
        print("Rollback completed. Backup reinstated.")
        logger.info("Rollback completed. Backup reinstated.")

def main():
    logger.info("Starting main function.")
    parser = argparse.ArgumentParser(description="Deploy a GitHub repository.")
    parser.add_argument("--rollback", action="store_true", help="Perform rollback using the backup.")
    args = parser.parse_args()

    git_url = input("Enter the GitHub repository URL: ").strip()
    base_destination_path = input("Enter the base destination path for the repository: ").strip()
    branch = input("Enter the branch name to deploy (default is 'master'): ").strip() or "master"
    github_token = getpass.getpass("Enter your GitHub Personal Access Token: ").strip()
    backup_base_path = input("Enter the base path for the backup: ").strip()

    repo_name = os.path.basename(git_url).replace('.git', '')
    backup_repo_path = os.path.join(backup_base_path, repo_name)
    destination_path = os.path.join(base_destination_path, repo_name)

    if args.rollback:
        if os.path.exists(backup_repo_path):
            restore_backup(backup_repo_path, destination_path)
        else:
            print("Backup path does not exist. Rollback failed.")
            logger.error("Backup path does not exist. Rollback failed.")
    else:
        deploy_repo(git_url, base_destination_path, branch, github_token, backup_base_path)

if __name__ == "__main__":
    main()
