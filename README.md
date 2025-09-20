# ICT2114

## Linux Ubuntu

### Create Python Virtual Environment

```bash
python3 -m venv .venv
```

### Activate and Deactivate the environment

```bash
source .venv/bin/activate
deactivate
```

### Install Dependencies from requirements.txt

```bat
pip install -r ./modularized/requirements.txt
```

------------------------------------------------------------------


Create an environment

```bat
python -m venv .venv
```

Activate the environment

```bat
.venv\Scripts\activate
```

Deactivate the environment

```bat
.venv\Scripts\deactivate
```

Run the Flask app

```bat
python app.py
```

OPTIONAL: export all install package into requirements.txt

```bat
pip freeze > requirements.txt
```

Install Dependencies from requirements.txt

```bat
pip install -r requirements.txt
```
