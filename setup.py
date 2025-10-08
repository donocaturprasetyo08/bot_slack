#!/usr/bin/env python3
"""
Setup script for Slack Thread Analyzer Bot
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="slack-thread-analyzer",
    version="1.0.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="Slack bot for analyzing threads with Gemini AI and saving to Google Sheets",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/slack-thread-analyzer",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "slack-sdk>=3.23.0",
        "google-auth>=2.23.4",
        "google-auth-oauthlib>=1.1.0",
        "google-auth-httplib2>=0.2.0",
        "google-api-python-client>=2.108.0",
        "google-generativeai>=0.3.2",
        "python-dotenv>=1.0.0",
        "flask>=2.3.3",
        "gunicorn>=21.2.0",
        "requests>=2.31.0",
        "pyngrok>=7.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "black>=22.0.0",
            "flake8>=4.0.0",
            "mypy>=0.950",
        ],
    },
    entry_points={
        "console_scripts": [
            "slack-thread-analyzer=apps:main",
        ],
    },
)