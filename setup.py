from setuptools import setup, find_packages

install_requirements = ['six>=1.4', 'pytz', 'tzlocal']

version = '1.2.0'

try:
    import importlib
except ImportError:
    install_requirements.append('importlib')

setup(
    name='tasklib',
    version=version,
    description='Python Task Warrior library',
    long_description=open('README.rst').read(),
    author='Rob Golding',
    author_email='rob@robgolding.com',
    license='BSD',
    url='https://github.com/robgolding63/tasklib',
    download_url='https://github.com/robgolding63/tasklib/downloads',
    packages=find_packages(),
    include_package_data=True,
    test_suite='tasklib.tests',
    install_requires=install_requirements,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Programming Language :: Python',
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.6",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.2",
        "Programming Language :: Python :: 3.3",
        'License :: OSI Approved :: BSD License',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Intended Audience :: Developers',
    ],
)
