from setuptools import setup, find_packages

setup(
    name="ats-network",
    version="1.0.0",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "app": ["templates/email/*.html"],
    },
    install_requires=[
        "fastapi",
        "uvicorn",
        "jinja2",
        "python-jose",
        "passlib",
        "python-multipart",
        "fastapi-mail",
        "motor",
        "pydantic",
        "pydantic-settings",
        "python-jose[cryptography]",
        "redis",
        "aiofiles",
        "python-magic"
    ],
)