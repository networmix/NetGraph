from setuptools import setup, find_packages


with open("README.md", encoding="utf8") as f:
    readme = f.read()

with open("LICENSE", encoding="utf8") as f:
    lic = f.read()

setup(
    name="NetGraph",
    version="0.1.0",
    description="Simple graph library for network modeling and analysis.",
    long_description=readme,
    license=lic,
    packages=find_packages(exclude=("tests", "docs")),
    tests_require=['pytest'],
)
