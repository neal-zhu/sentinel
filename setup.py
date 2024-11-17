"""
Setup script for Sentinel package

Handles package dependencies and installation configuration.
"""

from setuptools import setup, find_packages

setup(
    name="sentinel",
    version="0.1",
    description="A flexible async blockchain event processing framework",
    author="Neal Zhu",
    packages=find_packages(),
    install_requires=[
        "web3>=7.0.0",
        "pydantic>=2.0.0",
        "loguru>=0.7.0",
        "tomli>=2.0.0",
        "tomli-w>=1.0.0",
        "wxpusher>=2.0.0",
        "hexbytes>=0.3.0",
        "aioetherscan>=0.9.0",
    ],
    python_requires=">=3.9",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
) 