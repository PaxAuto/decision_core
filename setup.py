from setuptools import setup

package_name = 'decision_core'

setup(
    name=package_name,
    version='0.0.1',  
    packages=['decision_core'],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools', 'rclpy', 'transitions'],  
    zip_safe=True,
    maintainer='Harsh Mukeshbhai Bhadani',  
    maintainer_email='har8774s@hs-coburg.de',  
    description='Decision Core component for state machine implementation using FSM and transitions framework.',
    license='Apache-2.0', 
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'decision_core = decision_core.decision_core:main',  
        ],
    },
)
