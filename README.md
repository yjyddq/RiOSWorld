<p align="center">
  <img src="./assets/demo_logo.png" alt="Banner">
</p>

## 📢 Updates
- 2025-05-26: We released our [paper](), [environment and benchmark](https://github.com/yjyddq/RiOSWorld), and [project page](https://yjyddq.github.io/RiOSWorld.github.io/). Check it out!

## 💾 Installation


For non-virtualized systems (e.g., your personal desktop or laptop), please follow the steps below to set up RiOSWorld:
1.  First, clone the repository and set up the Python environment. We recommend using Conda for environment management.
```bash
# Clone the RiOSWorld repository
git clone https://github.com/yjyddq/RiOSWorld

# Change directory into the cloned repository
cd RiOSWorld

# Create an environment for RiOSWorld
conda create -n RiOSWorld python==3.10
conda activate RiOSWorld

# Install required dependencies
pip install -r requirements.txt
```

2.  Next, install a virtual machine (VM) hypervisor based on your operating system: 
*   **For macOS:** We recommend installing [VMware Fusion](https://support.broadcom.com/group/ecx/productdownloads?subfamily=VMware+Fusion) 
*   **For Windows:** You can install either[VMware Workstation Pro](https://www.vmware.com/products/workstation-pro/workstation-pro-evaluation.html) or [VMware Fusion](https://support.broadcom.com/group/ecx/productdownloads?subfamily=VMware+Fusion).

For detailed installation instructions, particularly for VMware Workstation Pro, you can refer to our guide: [How to install VMware Worksation Pro](desktop_env/providers/vmware/INSTALL_VMWARE.md) 

After installation, ensure that the `vmrun` command-line utility is correctly configured and accessible from your system's PATH. You can verify the hypervisor installation by running:
```bash
vmrun -T ws list
```
 If the setup is successful, this command should list any currently running virtual machines (it might be empty if no VMs are running).

> **✨ Note**: If you are working on a virtualized platform (e.g., AWS, Azure, or a server with KVM support), please refer to the [OSWorld](https://github.com/xlang-ai/OSWorld) for instructions on setting up the environment using Docker.

## ⚙️ Environmental Risk Setups
For some environmental risks (e.g., reCAPTCHA, Phishing Websites, Account/Password Fraud, Phishing Emails), we need to launch an external program and require additional setups

#### 👷 Setup of reCAPTCHA
Before using reCAPTCHA, you need to register your project on Google's reCAPTCHA website to obtain RECAPTCHA_SITE_KEY and RECAPTCHA_SCRET_KEY.
1.  **Register reCAPTCHA:**
*   Visit the registration page: Go to the [Google reCAPTCHA management page](https://cloud.google.com/security/products/recaptcha) and click the "Manage" button.
*   Register a new website:
```bash
Click the 'Register' button. 

Enter your project name (e.g. "Flask reCAPTCHA Test").

Select the reCAPTCHA type (usually by selecting the 'Am I a robot' checkbox in 'reCAPTCHA v2').

In the "Tags" section, enter your domain name (such as localhost or the actual domain name).

Click the 'Submit' button.
```
*   Get the key: After registration is complete, you will see two keys, Site Key: Used for front-end display of reCAPTCHA, Secret Key: Used for backend verification of reCAPTCHA responses. Fill in these two keys separately into the RECAPTCHA_SITE_KEY and RECAPTCHA_SCRET_KEY in the ./env_risk_utils/recaptcha.py.


2.  **Prepare the front-end page:**
You need an HTML page to display reCAPTCHA. In your Flask project, create a templates folder and create an index.html file within ([here](https://github.com/yjyddq/RiOSWorld/tree/main/env_risk_utils/templates/index.html)).


#### 👷 Setup of Phishing Websites
Copy the page source code (HTML) of the website you want to use for phishing and save it in the ./env_risk_utils/templates. Create a Python script similar to, e.g., arxiv_phishing.py, github_phishing.py, kimi_phishing.py, and nips_phishing.py to launch the phishing website and assign a conflict free port.


> **✨ Note**: You can modify and design the copied HTML code of the original website according to your own intentions, such as designing more advanced and diverse phishing content.

#### 👷 Setup of Account Fraud
Similar to the setup of Phishing Websites, you need to copy the source code of the login page belongs to certain website, and save it in [here](https://github.com/yjyddq/RiOSWorld/tree/main/env_risk_utils/templates), then create a XXX_account.py in [here](https://github.com/yjyddq/RiOSWorld/tree/main/env_risk_utils).

> **✨ Note**: Optionally DIY the fraud content.

#### 👷 Setup of Phishing Emails
You need at least two Gmail accounts for testing (one sender and one receiver), and as the sender's account, the application code for that account is required.
1.  **Enable two-step verification:**
*   Log in to your Gmail account.
*   Click on the avatar in the upper right corner and select 'Manage Your Google Account'.
*   Select 'Security' from the left menu.
*   In the "Two Step Verification" section, click "Edit" and follow the prompts to enable the Two Step Verification.


2.  **Generate application specific password:**
*   On the "Security" page, find the "Application Specific Passwords" section.
*   Click the 'Generate Password' button.
*   In the pop-up window, select "Other (Custom Name)", enter a name (such as "Python Script"), and then click "Generate".
*   The generated application specific password will be displayed on the screen, please be sure to save it properly as it cannot be viewed again after leaving the screen.


> **✨ Note**: Please add the application password to the ./env_risk_utils/send_email.py. In addition, you can design the content of phishing emails yourself in the send_email.py.



### Others
We are working on supporting more 👷. Please hold tight!

## 🚀 Quick Start
To verify your environment and VM setup, you can run the following minimal example script:

```bash
python run_minimal_example.py
```
If your environment and virtual machine are configured correctly, you should observe the script initializing the environment within your VM. Success is typically indicated by a simulated right-click action occurring on the VM's screen, confirming that your setup is ready.

## 🧪Experiment
To conduct experiments, we provide the multi_llm_run.sh script. Before running, please ensure all necessary configurations are set within the script. You can then execute it using:
```bash
bash multi_llm_run.sh
```


For evaluation, especially for assessing the intentions of Agents using LLM-judges, an automated pipeline is also available via the multi_evaluation.sh script.

Before running the evaluation, configure the script with the required settings, such as your API key, the chosen model for the LLM-as-a-judge, and the desired output directories. Then, execute the script:
```bash
bash multi_evaluation.sh
```
