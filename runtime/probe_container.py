"""Finite real Docker boundary probes. Never calls a model."""
import argparse
from pathlib import Path
from container_boundary import DockerBoundary, resource_probe


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--docker', default='/usr/local/bin/docker')
    p.add_argument('--endpoint', required=True)
    p.add_argument('--client-config', required=True, type=Path)
    p.add_argument('--image', required=True)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    b = DockerBoundary(a.docker, a.endpoint, a.client_config, a.image, a.output)
    print(resource_probe(b))


if __name__ == '__main__': main()
