# ICT2114

Create an environment

```bat
py -3.10 -m venv .venv
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