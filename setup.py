from setuptools import setup, find_packages

version = '0.7.0'

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
    install_requires=['six==1.5.2'],
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
