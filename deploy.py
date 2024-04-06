import logging
import os
import shutil
import subprocess
from datetime import datetime
import smtplib
from email.message import EmailMessage

# Setup Logging
logging.basicConfig(filename='deployment.log', level=logging.INFO, format='%(asctime)s:%(levelname)s:%(message)s')

# Email Settings - fill in with your details
SMTP_SERVER = 'smtp.example.com'
SMTP_PORT = 587  # For SSL: 465, for TLS/STARTTLS: 587
SMTP_USERNAME = 'your_email@example.com'
SMTP_PASSWORD = 'your_password'
EMAIL_FROM = 'your_email@example.com'
EMAIL_TO = 'recipient_email@example.com'
EMAIL_SUBJECT = 'Deployment Notification'

def send_email(body):
    """Sends an email with the specified body text."""
    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = EMAIL_SUBJECT
    msg['From'] = EMAIL_FROM
    msg['To'] = EMAIL_TO

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
            smtp.starttls()  # Secure the connection
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(msg)
        logging.info("Email notification sent successfully.")
    except Exception as e:
        logging.error(f"Failed to send email notification: {e}")

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

def branch_exists(git_url, branch):
    """Checks if the specified branch exists in the remote repository."""
    try:
        output = subprocess.check_output(["git", "ls-remote", "--heads", git_url, branch])
        return bool(output)
    except subprocess.CalledProcessError:
        return False

def get_current_branch(destination_path):
    """Returns the current branch name of the repository at the given destination path."""
    try:
        os.chdir(destination_path)  # Change to the destination directory
        branch_name = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).decode('utf-8').strip()
        return branch_name
    except subprocess.CalledProcessError:
        logging.error("Error retrieving the current branch name.")
        return None

def clone_repo(git_url, destination_path, branch="master"):
    """Clones the given GitHub repository into the specified destination path and checks out the specified branch."""
    if branch_exists(git_url, branch):
        if not os.path.exists(destination_path):
            os.makedirs(destination_path)
        command = ["git", "clone", "-b", branch, git_url, destination_path]
        try:
            subprocess.run(command, check=True)
            logging.info(f"Repository cloned successfully into {destination_path} on branch '{branch}'.")
        except subprocess.CalledProcessError as e:
            logging.error(f"Error cloning repository: {e}")
            send_email(f"Deployment failed for repository {git_url} on branch {branch}. Error: {e}")
    else:
        logging.error(f"Error: The branch '{branch}' does not exist in the remote repository.")
        send_email(f"Deployment failed: The branch '{branch}' does not exist in the remote repository {git_url}.")

def update_repo(git_url, destination_path, branch="master"):
    """Updates the repository at the destination path."""
    current_branch = get_current_branch(destination_path)
    if current_branch == branch:
        try:
            subprocess.run(["git", "pull", "origin", branch], check=True)
            logging.info(f"Updated the repository in {destination_path} to the latest version of branch '{branch}'.")
        except subprocess.CalledProcessError as e:
            logging.error(f"Error updating repository: {e}")
            send_email(f"Deployment update failed for repository {git_url} on branch {branch}. Error: {e}")
    else:
        clone_repo(git_url, destination_path, branch)

def deploy_repo():
    git_url = input("Enter the GitHub repository URL: ")
    destination_path = input("Enter the destination path for the repository: ")
    branch = input("Enter the branch name to deploy (default is 'master'): ") or "master"

    if os.path.exists(destination_path) and os.path.exists(os.path.join(destination_path, '.git')):
        # Backup current deployment before making any changes
        backup_path = backup_artifacts(destination_path)
        if backup_path:
            update_repo(git_url, destination_path, branch)
            send_email(f"Deployment updated successfully for repository {git_url} on branch {branch}. Backup created at {backup_path}.")
        else:
            logging.error("Backup failed. Deployment aborted.")
            send_email("Deployment aborted due to backup failure.")
    else:
        clone_repo(git_url, destination_path, branch)
        send_email(f"Repository {git_url} cloned successfully into {destination_path} on branch '{branch}'.")

if __name__ == "__main__":
    deploy_repo()
