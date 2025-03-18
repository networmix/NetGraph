from setuptools import setup, find_packages


with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="ngraph",
    version="0.6.0",
    author="Andrey Golovanov",
    description="A library for network modeling and capacity analysis.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/networmix/netgraph",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    packages=find_packages(exclude=("tests", "dev", "examples")),
    python_requires=">=3.13",
    tests_require=["pytest", "networkx"],
)
