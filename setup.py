from setuptools import setup, find_packages

setup(
    name="sentinel",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "web3",
        "pydantic",
        "loguru",
        "tomli",
        "wxpusher",
        "hexbytes",
    ],
) 