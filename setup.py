from setuptools import setup

setup(
    name="java_parser",
    version="0.1",
    py_modules=['analyze'],
    install_requires=[
        'javalang==0.13.0',
        'networkx==3.1',
        'graphviz==0.20.1',
        'pydantic==2.5.1'
    ],
    entry_points={
        'console_scripts': [
            'java-parser=analyze:main',
        ],
    }
)
