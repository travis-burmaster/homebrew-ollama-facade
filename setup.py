from setuptools import setup, find_packages

setup(
    name="ollama-facade",
    version="1.0.0",
    description="Run Claude Max as a local Ollama server on your network",
    author="Travis Burmaster",
    url="https://github.com/travis-burmaster/ollama-facade",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "fastapi>=0.110.0",
        "uvicorn[standard]>=0.29.0",
        "httpx>=0.27.0",
        "pyyaml>=6.0",
        "curl-cffi>=0.7.0",
    ],
    entry_points={
        "console_scripts": [
            "ollama-facade=ollama_facade.cli:main",
        ],
    },
)
