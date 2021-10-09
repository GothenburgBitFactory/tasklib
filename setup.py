from setuptools import setup, find_packages

install_requirements = ['pytz', 'tzlocal']

version = '2.4.0'

try:
    import importlib
except ImportError:
    install_requirements.append('importlib')

setup(
    name='tasklib',
    version=version,
    description='Official Taskwarrior library for Python',
    long_description=open('README.rst').read(),
    author='GothenburgBitFactory',
    author_email='support@gothenburgbitfactory.org',
    license='BSD',
    url='https://github.com/GothenburgBitFactory/tasklib',
    download_url='https://github.com/GothenburgBitFactory/tasklib/downloads',
    packages=find_packages(),
    include_package_data=True,
    test_suite='tasklib.tests',
    install_requires=install_requirements,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Programming Language :: Python',
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        'License :: OSI Approved :: BSD License',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Intended Audience :: Developers',
    ],
)
