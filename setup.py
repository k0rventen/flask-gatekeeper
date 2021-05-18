import setuptools


with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="flask_gatekeeper",
    version="0.3.1",
    author="k0rventen",
    python_requires='>=3.7',
    description="A (very) simple banning & rate limiting extension for Flask.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="MIT",
    url="https://github.com/k0rventen/flask-gatekeeper",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
    ],
    install_requires=[
        'Flask>=1.1.*',
    ],
)
