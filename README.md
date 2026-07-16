# Setup

### uv Installation
**mac installation**
```sh
brew install uv
```
**windows installation (with winget)**
```sh
winget install --id=astral-sh.uv  -e
```
> Other installation options can be found in the [documentation](https://docs.astral.sh/uv/getting-started/installation/)  
> ***Note**: installing with **pip** may cause issues with installing custom modules*
---
### Setup & Sync Workspace
>After installing uv, ensure to restart the terminal before running the following  

**Sync Dependencies and Configurations**  
This command is used to ensure all project dependencies are installed and sets up the virtual environment for the workspace
```sh
uv sync
```
**Install Project Modules**  
The following is used to ensure that packages in the **/src/** are packaged properly and callable
```sh
uv pip install -e .
```

---

### Other Commands

**Jupyter Notebook Kernel Setup**  
With the virtual environment active, run the following to register the environment's kernel with Jupyter (name can be replaced)
```sh
uv run python -m ipykernel install --user --name=tba
```
To open Jupyter Notebook, simply run:
```sh
uv run jupyter notebook
```
Select the kernel from the dropdown menu if prompted or simply change the kernel by clicking on the button left of the hamburger dropdown menu at the top right of any notebook

**Run Files In Virtual Environment**  
To run a file within the virtual environment, use the following command:
```sh
uv run <filename>
```
If the command doesn't work, manually select the relative interpreter or run the command in the bash terminal



## Sources
https://open.toronto.ca/dataset/bike-share-toronto/  
https://open.toronto.ca/dataset/bike-share-toronto-ridership-data/  
https://open.toronto.ca/dataset/cycling-network/
https://bikeshare-research.org/#bssid:toronto:data -> https://tor.publicbikesystem.net/ube/gbfs/v1/
https://gbfs.org/documentation/reference/