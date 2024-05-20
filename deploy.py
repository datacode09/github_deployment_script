import logging
import os
import shutil
import subprocess
import argparse

# Setup Logging
logger = logging.getLogger('DeploymentLogger')
logger.setLevel(logging.INFO)
handler = logging.FileHandler('deployment.log')
formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def verify_git_installation():
    """Check if Git is installed."""
    try:
        subprocess.check_output(["git", "--version"])
        logger.info("Git is installed.")
    except subprocess.CalledProcessError as e:
        logger.error("Git is not installed. Please install Git to proceed.")
        raise EnvironmentError("Git is not installed. Please install Git to proceed.") from e

def backup_artifacts(destination_path, backup_repo_path):
    """Backs up the deployment artifacts."""
    try:
        if os.path.exists(destination_path):
            if os.path.exists(backup_repo_path):
                shutil.rmtree(backup_repo_path)  # Remove the existing backup directory
            shutil.copytree(destination_path, backup_repo_path)
            logger.info(f"Backup created at: {backup_repo_path}")
            return backup_repo_path
    except shutil.Error as e:
        logger.error(f"Error creating backup: shutil error occurred - {e}")
        return None
    except Exception as e:
        logger.error(f"Error creating backup: unexpected error occurred - {e}")
        return None

def restore_backup(backup_repo_path, destination_path):
    """Restores the backup in case of deployment failure."""
    try:
        if os.path.exists(destination_path):
            shutil.rmtree(destination_path)
        shutil.copytree(backup_repo_path, destination_path)
        logger.info(f"Backup restored from {backup_repo_path} to {destination_path}")
        print(f"Backup restored from {backup_repo_path} to {destination_path}")
    except shutil.Error as e:
        logger.error(f"Error restoring backup: shutil error occurred - {e}")
        print(f"Error restoring backup: shutil error occurred - {e}")
    except Exception as e:
        logger.error(f"Error restoring backup: unexpected error occurred - {e}")
        print(f"Error restoring backup: unexpected error occurred - {e}")

def branch_exists(git_url, branch, github_token):
    """Checks if the specified branch exists in the remote repository."""
    auth_git_url = git_url.replace("https://", f"https://{github_token}@")
    try:
        output = subprocess.check_output(["git", "ls-remote", "--heads", auth_git_url, branch])
        return bool(output)
    except subprocess.CalledProcessError as e:
        logger.error(f"Error checking branch existence: {e}")
        return False

def get_current_branch(destination_path):
    """Returns the current branch name of the repository at the given destination path."""
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

def clone_repo(git_url, destination_path, branch, github_token):
    """Clones the given GitHub repository into the specified destination path and checks out the specified branch."""
    auth_git_url = git_url.replace("https://", f"https://{github_token}@")
    if branch_exists(git_url, branch, github_token):
        if not os.path.exists(destination_path):
            os.makedirs(destination_path)
        command = ["git", "clone", "-b", branch, auth_git_url, destination_path]
        try:
            subprocess.run(command, check=True)
            logger.info(f"Repository cloned successfully into {destination_path} on branch '{branch}'.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Error cloning repository: subprocess error occurred - {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error occurred while cloning repository: {e}")
            raise
    else:
        logger.error(f"Error: The branch '{branch}' does not exist in the remote repository.")
        raise ValueError(f"The branch '{branch}' does not exist in the remote repository.")

def deploy_repo(git_url, destination_path, branch, github_token, backup_base_path):
    verify_git_installation()

    backup_repo_path = os.path.join(backup_base_path, os.path.basename(destination_path))
    
    if not os.path.isdir(destination_path):
        logger.error("The destination path is not a valid directory.")
        print("The destination path is not a valid directory.")
        return

    rollback_needed = False

    if os.path.exists(destination_path):
        # Backup current deployment before making any changes
        backup_repo_path = backup_artifacts(destination_path, backup_repo_path)
        if backup_repo_path:
            try:
                # Clean the destination path
                shutil.rmtree(destination_path)
                os.makedirs(destination_path)
                # Clone the repository
                clone_repo(git_url, destination_path, branch, github_token)
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
        if not os.path.exists(destination_path):
            os.makedirs(destination_path)
        try:
            clone_repo(git_url, destination_path, branch, github_token)
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
    parser = argparse.ArgumentParser(description="Deploy a GitHub repository.")
    parser.add_argument("--rollback", action="store_true", help="Perform rollback using the backup.")
    args = parser.parse_args()

    git_url = input("Enter the GitHub repository URL: ").strip()
    destination_path = input("Enter the destination path for the repository: ").strip()
    branch = input("Enter the branch name to deploy (default is 'master'): ").strip() or "master"
    github_token = input("Enter your GitHub Personal Access Token: ").strip()
    backup_base_path = input("Enter the path for the backup: ").strip()

    if args.rollback:
        backup_repo_path = os.path.join(backup_base_path, os.path.basename(destination_path))
        if os.path.exists(backup_repo_path):
            restore_backup(backup_repo_path, destination_path)
        else:
            print("Backup path does not exist. Rollback failed.")
            logger.error("Backup path does not exist. Rollback failed.")
    else:
        deploy_repo(git_url, destination_path, branch, github_token, backup_base_path)

if __name__ == "__main__":
    main()
