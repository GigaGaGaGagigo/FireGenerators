from setuptools import find_packages, setup

setup(
    name="firegen",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "streamlit",
        "langgraph",
        "langchain",
        # 기타 필요한 패키지들
    ],
    python_requires=">=3.8",
)
