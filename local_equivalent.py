#!/usr/bin/env python3
import os
import shutil
import subprocess
import argparse

all_platforms = [
    'centos7_gcc9',
    'centos7_gcc10',
    'ubuntu2004_gcc10',
    'macos1015_xcode11',
    'macos1015_xcode12',
    'macos11_xcode12_arm',
    'win2019_vs2019',
    'win2019_msys',  # (this is used for building a few buildtools)
]

conan_env = dict(os.environ)
conan_exe = 'conan'
if not shutil.which(conan_exe):
    raise Exception(f'Please install {conan_exe} first')

jfrog_cli = 'jfrog'
if not shutil.which(jfrog_cli):
    raise Exception(f'Please install {jfrog_cli} first')

if 'CCDC_USERNAME' in os.environ:
    artifactory_user = os.environ['CCDC_USERNAME']
elif 'USER' in os.environ:
    artifactory_user = os.environ['USER']
elif 'USERNAME' in os.environ:
    artifactory_user = os.environ['USERNAME']
artifactory_api_key = os.environ["ARTIFACTORY_API_KEY"]

conan_env['CONAN_LOGIN_USERNAME'] = artifactory_user
conan_env['CONAN_PASSWORD'] = artifactory_api_key


def run_command(args):
    print(f'Running {" ".join(args)}')
    subprocess.run(args=args, env=conan_env)

def run_conan(args):
    conan_args = [conan_exe] + args
    run_command(conan_args)


def build_conan_package(package, package_version, local_recipe, platform,
                        build_types=['Release', 'Debug', 'RelWithDebInfo'],
                        source_repository='public-conan-center',
                        destination_repository='ccdc-3rdparty-conan',
                        macos_brew_preinstall=[],
                        centos_yum_preinstall=[],
                        macos_deployment_target='10.13',
                        macos_xcode_version='12.4',
                        windows_bash_path=None,
                        conan_logging_level='info',
                        workaround_autotools_windows_debug_issue=False,
                        use_release_zlib_profile=False,
                        really_upload=False,
                        ):

    # conan_env['CONAN_LOGGING_LEVEL']='critical'
    # conan_env['CONAN_USER_HOME']='.conan'

    if '@' not in package_version:
        package_version = package_version+'@'

    if 'centos' in platform:
        if centos_yum_preinstall:
            all_yum = ' '.join(centos_yum_preinstall)
            print(f'Installing {all_yum} with yum')
            os.system(f"sudo yum install -y { all_yum }")

    if 'macos' in platform:
        if macos_brew_preinstall:
            all_brew = ' '.join(macos_brew_preinstall)
            print(f'Installing {all_brew} with brew')
            os.system(f"brew install { all_brew }")
        if macos_xcode_version:
            print(
                f"sudo xcode-select -s /Applications/Xcode_{ macos_xcode_version }.app/Contents/Developer")
            os.system(
                f"sudo xcode-select -s /Applications/Xcode_{ macos_xcode_version }.app/Contents/Developer")
        conan_env['MACOSX_DEPLOYMENT_TARGET'] = macos_deployment_target

    if 'win' in platform:
        # The templates remove some tools and add missing certificates
        # we won't repeat that here
        print('building for windows')
        if windows_bash_path:
            conan_env['CONAN_BASH_PATH'] = windows_bash_path
        if workaround_autotools_windows_debug_issue:
            conan_env['CONAN_CPU_COUNT'] = 1

    if platform == 'centos7_gcc9':
        conan_profile = 'centos7-gcc9-x86_64'
        docker_container = 'rockdreamer/centos7-gcc9:latest'
    if platform == 'centos7_gcc10':
        conan_profile = 'centos7-gcc10-x86_64'
        docker_container = 'rockdreamer/centos7-gcc10:latest'
    if platform == 'ubuntu2004_gcc10':
        conan_profile = 'ubuntu20-gcc10-x86_64'
        docker_container = 'rockdreamer/ubuntu20-gcc10:latest'

    if platform == 'macos1015_xcode11':
        conan_profile = 'macos-xcode11-x86_64'
    if platform == 'macos1015_xcode12':
        conan_profile = 'macos-xcode12-x86_64'
    if platform == 'macos11_xcode12_arm':
        conan_profile = 'macos-xcode12-armv8'

    if platform == 'win2019_vs2019':
        conan_profile = 'windows-msvc16-amd64'
    if platform == 'win2019_msys':
        conan_profile = 'windows-msys-amd64'

    run_conan([
        'config',
        'install',
        f'https://{artifactory_user}:{artifactory_api_key}@artifactory.ccdc.cam.ac.uk/artifactory/ccdc-conan-metadata/common-3rdparty-config.zip'
    ])

    if local_recipe:
        run_conan([
            'export',
            local_recipe,
            f'{package_version}',
        ])
    else:
        # Download just this package from the source repository, dependencies must already be built in the destination
        run_conan([
            'download',
            f'{package}/{package_version}',
            f'--remote={ source_repository }',
            '--recipe'
        ])

    for build_type in build_types:
        additional_profiles = []
        if use_release_zlib_profile:
            if 'msvc16' in conan_profile:
                additional_profiles.append('windows-msvc16-release-zlib')

        conan_install_args = [
            'install',
            f'{package}/{package_version}',
        ]
        if build_type == 'Debug':
            conan_install_args += ['--profile', f'{conan_profile}-debug']
        else:
            conan_install_args += ['--profile', f'{conan_profile}-release']
        for additional_profile in additional_profiles:
            conan_install_args += ['--profile', additional_profile]
        conan_install_args += [
            f'--remote={destination_repository }',
            f'--build={ package }',
            '-s',
            f'build_type={ build_type }',
        ]
        run_conan(conan_install_args)

        if local_recipe:
            conan_test_args = [
                'test',
                f'{local_recipe}/test_package',
                f'{package}/{package_version}',
            ]
            if 'windows' in conan_profile:
                if build_type == 'Debug':
                    conan_test_args += ['--profile', f'{conan_profile}-debug']
                else:
                    conan_test_args += ['--profile',
                                        f'{conan_profile}-release']
            else:
                conan_test_args += ['--profile', conan_profile]
            for additional_profile in additional_profiles:
                conan_test_args += ['--profile', additional_profile]
            conan_test_args += [
                '-s',
                f'build_type={ build_type }',
            ]
            run_conan(conan_test_args)

    if really_upload:
        run_conan([
            'upload',
            f'{package}/{package_version}',
            '--all',
            f'--remote={ destination_repository }',
        ])


def main():
    parser = argparse.ArgumentParser(description='Build a conan package.')
    parser.add_argument('package', help='the name of the conan package')
    parser.add_argument('package_version',
                        help='the version of the conan package')
    parser.add_argument(
        '--platform', help='the version of the conan package', choices=all_platforms)
    parser.add_argument('--build-types', help='well, build types',
                        action='append', choices=['Release', 'Debug', 'RelWithDebInfo'])
    parser.add_argument('--source-repository',
                        help='where the build comes from', default='public-conan-center')
    parser.add_argument('--destination-repository',
                        help='where the build goes', default='ccdc-3rdparty-conan')
    parser.add_argument('--macos-brew-preinstall',
                        help='install brew packages', action='append')
    parser.add_argument('--centos-yum-preinstall',
                        help='install yum packages', action='append')
    parser.add_argument('--macos-deployment-target',
                        help='minimum supported macos version', default='10.13')
    parser.add_argument('--macos-xcode-version',
                        help='xcode version')
    parser.add_argument('--windows-bash-path',
                        help='workaround for recipes needing specific path to bash')
    parser.add_argument('--conan-logging-level', help='', default='info')
    parser.add_argument(
        '--workaround-autotools-windows-debug-issue', help='', action='store_true')
    parser.add_argument('--use-release-zlib-profile',
                        help='', action='store_true')
    parser.add_argument(
        '--local-recipe', help='directory that contains conanfile.py')
    parser.add_argument(
        '--really-upload', help='really upload to artifactory', action='store_true')
    args = parser.parse_args()
    if not args.build_types:
        build_types = ['Release', 'Debug', 'RelWithDebInfo']
    else:
        build_types = [x for x in args.build_types]
    if not args.macos_brew_preinstall:
        macos_brew_preinstall = []
    else:
        macos_brew_preinstall = list(args.macos_brew_preinstall)
    if not args.centos_yum_preinstall:
        centos_yum_preinstall = []
    else:
        centos_yum_preinstall = list(args.centos_yum_preinstall)
    try:
        build_conan_package(
            package=args.package,
            package_version=args.package_version,
            local_recipe=args.local_recipe,
            platform=args.platform,
            build_types=build_types,
            source_repository=args.source_repository,
            destination_repository=args.destination_repository,
            macos_brew_preinstall=macos_brew_preinstall,
            centos_yum_preinstall=centos_yum_preinstall,
            macos_deployment_target=args.macos_deployment_target,
            macos_xcode_version=args.macos_xcode_version,
            windows_bash_path=args.windows_bash_path,
            conan_logging_level=args.conan_logging_level,
            workaround_autotools_windows_debug_issue=args.workaround_autotools_windows_debug_issue,
            use_release_zlib_profile=args.use_release_zlib_profile,
            really_upload=args.really_upload,
        )
    except subprocess.CalledProcessError as e:
        print(f'Last command output was {e.output.decode(errors="replace")}')


if __name__ == "__main__":
    main()
