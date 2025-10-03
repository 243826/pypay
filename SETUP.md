Install desired version (installs in $HOME/.pyenv/versions):

pyenv install 3.11.10

Create the project directory and change dir:

mkdir myproject
cd myproject

Set the python version for the project directory to some installed version (creates a local file .python-version):

pyenv local 3.11.10

Invoke venv through pyenv:

pyenv exec python3 -m venv .venv

Activate virtual environment:

source .venv/bin/activate

Confirm your python path (it should be pointing to something like $HOME/.pyenv/versions/3.11.10/bin/python3):

ls -al `which python3`

Confirm your python version:

python -V

pyenv exec pip install -r requirements.txt

pyenv exec python load.py work now.
