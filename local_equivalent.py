#!/usr/bin/env python3
import os
import shutil
import subprocess
import argparse
import sys


all_platforms = [
    'centos7_gcc10',
    'ubuntu2004_gcc10',
    'debian_bullseye_gcc10_armv7hf',
    'macos11_xcode12',
    'macos12_xcode13',
    'macos11_xcode13_arm',
    'win2019_vs2019',
    'win2019_msys',  # (this is used for building a few buildtools)
]

conan_env = dict(os.environ)
conan_exe = shutil.which('conan')
if not conan_exe:
    raise Exception(f'Please install conan first')

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

original_path = os.environ['PATH']
if '/opt/homebrew/bin' in original_path:
    conan_env['PATH'] = original_path.replace('/opt/homebrew/bin', '/opt/homebrew/opt/cmake/bin')
if '/usr/local/bin' in original_path and os.path.exists('/usr/local/opt/cmake/bin'):
    conan_env['PATH'] = original_path.replace('/usr/local/bin', '/usr/local/opt/cmake/bin')

if 'LD_LIBRARY_PATH' and '/opt/rh/rh-git29' in conan_env['PATH'] and '/opt/rh/httpd24/root/' not in conan_env['LD_LIBRARY_PATH']:
    conan_env['LD_LIBRARY_PATH']=conan_env['LD_LIBRARY_PATH']+':/opt/rh/httpd24/root/usr/lib64'

def run_command(args):
    print(f'Running {" ".join(args)}')
    subprocess.check_call(args=args, env=conan_env)


def run_conan(args):
    conan_args = [conan_exe] + args
    run_command(conan_args)


def build_conan_package(package, package_version, local_recipe, platform,
                        build_types=['Release', 'Debug', 'RelWithDebInfo'],
                        source_repository='public-conan-center',
                        destination_repository='ccdc-3rdparty-conan',
                        macos_brew_preinstall=[],
                        centos_yum_preinstall=[],
                        macos_deployment_target='11',
                        macos_xcode_version=None,
                        windows_bash_path=None,
                        conan_logging_level='info',
                        workaround_autotools_windows_debug_issue=False,
                        use_release_zlib_profile=False,
                        additional_profiles_for_all_platforms=[],
                        really_upload=False,
                        require_overrides=[],
                        configuration_branch='main',
                        configuration_local_directory=None,
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

    if platform == 'centos7_gcc10':
        conan_profile = 'centos7-gcc10-x86_64'
        conan_build_profile = 'build-on-centos7-gcc10-x86_64'
        # docker_container = 'rockdreamer/centos7-gcc10:latest'
    if platform == 'ubuntu2004_gcc10':
        conan_profile = 'ubuntu20-gcc10-x86_64'
        conan_build_profile = 'ubuntu20-gcc10-x86_64-release'
        # docker_container = 'rockdreamer/ubuntu20-gcc10:latest'
    if platform == 'debian_bullseye_gcc10_armv7hf':
        conan_profile = 'bullseye-gcc10-armv7hf'
        conan_build_profile = 'bullseye-gcc10-armv7hf-release'
        # docker_container = 'rockdreamer/bullseye-gcc10:latest'

    if platform == 'macos11_xcode12':
        conan_profile = 'macos-xcode12-x86_64'
        conan_build_profile = 'macos-xcode12-x86_64-release'
    if platform == 'macos12_xcode13':
        conan_profile = 'macos-xcode13-x86_64'
        conan_build_profile = 'macos-xcode13-x86_64-release'
    if platform == 'macos11_xcode13_arm':
        conan_profile = 'macos-xcode13-armv8'
        conan_build_profile = 'build-on-macos-xcode13-armv8'

    if platform == 'win2019_vs2019':
        conan_profile = 'windows-msvc16-amd64'
        conan_build_profile = 'windows-msvc16-amd64-release'
    if platform == 'win2019_msys':
        conan_profile = 'windows-msys-amd64'
        conan_build_profile = 'windows-msys-amd64-release'

    if configuration_local_directory:
        run_conan([
            'config',
            'install',
            configuration_local_directory,
        ])
    else:
        run_conan([
            'config',
            'install',
            'https://github.com/ccdc-opensource/conan-ccdc-common-configuration.git',
            '--type',
            'git',
            '--args',
            f'-b {configuration_branch}'
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
        additional_profiles.extend(additional_profiles_for_all_platforms)
        if use_release_zlib_profile:
            if 'msvc16' in conan_profile:
                additional_profiles.append('windows-msvc16-release-zlib')

        conan_install_args = [
            'install',
            f'{package}/{package_version}',
        ]

        if build_type == 'Debug':
            conan_install_args += ['--profile:build', f'{conan_build_profile}', '--profile:host', f'{conan_profile}-debug']
        else:
            conan_install_args += ['--profile:build', f'{conan_build_profile}', '--profile:host', f'{conan_profile}-release']
        for additional_profile in additional_profiles:
            conan_install_args += ['--profile', additional_profile]
        conan_install_args += [
            f'--remote={destination_repository }',
            f'--build={ package }',
            '-s',
            f'build_type={ build_type }',
        ]
        for override in require_overrides:
            conan_install_args += ['--require-override', override]
        run_conan(conan_install_args)

        if local_recipe:
            conan_test_args = [
                'test',
                f'{local_recipe}/test_package',
                f'{package}/{package_version}',
            ]
            if build_type == 'Debug':
                conan_test_args += ['--profile', f'{conan_profile}-debug']
            else:
                conan_test_args += ['--profile', f'{conan_profile}-release']
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
        '--platform', help='the platform to build for', required=True, choices=all_platforms)
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
                        help='minimum supported macos version', default='11')
    parser.add_argument('--macos-xcode-version',
                        help='xcode version')
    parser.add_argument('--windows-bash-path',
                        help='workaround for recipes needing specific path to bash')
    parser.add_argument('--conan-logging-level', help='', default='info')
    parser.add_argument(
        '--workaround-autotools-windows-debug-issue', help='', action='store_true')
    parser.add_argument('--use-release-zlib-profile',
                        help='', action='store_true')
    parser.add_argument('--additional-profiles-for-all-platforms',
                        help='Use additional profiles', action='append')
    parser.add_argument(
        '--local-recipe', help='directory that contains conanfile.py')
    parser.add_argument(
        '--really-upload', help='really upload to artifactory', action='store_true')
    parser.add_argument('--require-override',
                        help='override requirements for specific package', action='append')
    parser.add_argument('--configuration-branch',
                        help='Branch of ccdc-opensource/conan-ccdc-common-configuration to use', default='main')
    parser.add_argument('--configuration-local-directory',
                        help='checkout of ccdc-opensource/conan-ccdc-common-configuration to use')
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
    if not args.additional_profiles_for_all_platforms:
        additional_profiles_for_all_platforms = []
    else:
        additional_profiles_for_all_platforms = list(
            args.additional_profiles_for_all_platforms)
    if not args.require_override:
        require_overrides = []
    else:
        require_overrides = list(args.require_override)
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
            additional_profiles_for_all_platforms=additional_profiles_for_all_platforms,
            really_upload=args.really_upload,
            require_overrides=require_overrides,
            configuration_branch=args.configuration_branch,
            configuration_local_directory=args.configuration_local_directory,
        )
    except subprocess.CalledProcessError as e:
        if e.output:
            print(f'Last command output was {e.output.decode(errors="replace")}')
        sys.exit(1)


if __name__ == "__main__":
    main()
