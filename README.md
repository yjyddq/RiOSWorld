<p align="center">
  <img src="./assets/demo_logo.png" alt="Banner">
</p>

## 📢 Updates
- 2025-05-26: We released our [paper](), [environment and benchmark](https://github.com/yjyddq/RiOSWorld), and [project page](). Check it out!

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
*   **For macOS:** We recommend installing [VMware Fusion](https://support.broadcom.com/group/ecx/productdownloads?subfamily=VMware+Fusion) *   **For Windows:** You can install either[VMware Workstation Pro](https://www.vmware.com/products/workstation-pro/workstation-pro-evaluation.html) or [VMware Fusion](https://support.broadcom.com/group/ecx/productdownloads?subfamily=VMware+Fusion).

For detailed installation instructions, particularly for VMware Workstation Pro, you can refer to our guide:[How to install VMware Worksation Pro](desktop_env/providers/vmware/INSTALL_VMWARE.md) 

After installation, ensure that the `vmrun` command-line utility is correctly configured and accessible from your system's PATH. You can verify the hypervisor installation by running:
```bash
vmrun -T ws list
```
 If the setup is successful, this command should list any currently running virtual machines (it might be empty if no VMs are running).

> **Note**: If you are working on a virtualized platform (e.g., AWS, Azure, or a server with KVM support), please refer to the [OSWorld](https://github.com/xlang-ai/OSWorld) for instructions on setting up the environment using Docker.

## 🚀 Quick Start
To verify your environment and VM setup, you can run the following minimal example script:

```bash
python run_minimal_example.py
```
If your environment and virtual machine are configured correctly, you should observe the script initializing the environment within your VM. Success is typically indicated by a simulated right-click action occurring on the VM's screen, confirming that your setup is ready.

