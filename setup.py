from setuptools import setup, find_packages


with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="ngraph",
    version="0.0.2",
    author="Andrey Golovanov",
    description="A simple library for network modeling and analysis.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/networmix/netgraph",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    package_dir={"": "ngraph"},
    packages=find_packages(where=("ngraph")),
    python_requires=">=3.6",
    tests_require=["pytest"],
)
