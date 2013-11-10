from setuptools import setup, find_packages

setup(
    name='tasklib',
    version='0.2',
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
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: BSD License',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Programming Language :: Python',
        'Intended Audience :: Developers',
    ],
)
