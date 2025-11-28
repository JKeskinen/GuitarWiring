import sys
from pathlib import Path

# Add project root to sys.path so we can import the `app` folder
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import wiring


def pretty_print(name, d):
    print('---', name, '---')
    for k, v in d.items():
        print(f'{k}: {v}')
    print()


def main():
    # Neck measurements and probe mappings from user's setup
    neck = wiring.analyze_pickup(
        north_pair=['Green', 'Red'],
        south_pair=['Black', 'White'],
        north_probe='Laskee (käänteinen)',
        south_probe='Nousee (normaali)',
        north_swap=False,
        south_swap=False,
        bare=True,
        north_res_kohm=5.91,
        south_res_kohm=5.95,
        north_red_wire='Green',
        north_black_wire='Red',
        south_red_wire='White',
        south_black_wire='Black'
    )

    pretty_print('Neck analysis', neck)

    # Bridge measurements and probe mappings
    bridge = wiring.analyze_pickup(
        north_pair=['Red', 'Green'],
        south_pair=['Black', 'White'],
        north_probe='Laskee (käänteinen)',
        south_probe='Nousee (normaali)',
        north_swap=False,
        south_swap=False,
        bare=True,
        north_res_kohm=7.62,
        south_res_kohm=7.65,
        north_red_wire='Green',
        north_black_wire='Red',
        south_red_wire='White',
        south_black_wire='Black'
    )

    pretty_print('Bridge analysis', bridge)

    # Now compute mapping using the app/main.py rules (North START = HOT, North END + South END = Series, South START = Ground)
    def main_style_mapping(north_pair, south_pair, n_red, n_black, n_probe, n_swap, s_red, s_black, s_probe, s_swap, bare):
        nmap = wiring.infer_start_finish_from_probes(north_pair, n_red, n_black, n_probe, n_swap)
        smap = wiring.infer_start_finish_from_probes(south_pair, s_red, s_black, s_probe, s_swap)
        north_start = nmap.get('start')
        north_finish = nmap.get('finish')
        south_start = smap.get('start')
        south_finish = smap.get('finish')
        hot = north_start
        series = [x for x in [north_finish, south_finish] if x]
        ground = [x for x in ([south_start, 'Bare'] if bare else [south_start]) if x]
        return {'HOT': hot, 'SERIES_LINK': series, 'GROUND': ground}

    neck_main = main_style_mapping(
        ['Green', 'Red'], ['Black', 'White'],
        'Green', 'Red', 'Laskee (käänteinen)', False,
        'White', 'Black', 'Nousee (normaali)', False,
        True
    )
    pretty_print('Neck (main.py style) mapping', neck_main)

    bridge_main = main_style_mapping(
        ['Red', 'Green'], ['Black', 'White'],
        'Green', 'Red', 'Laskee (käänteinen)', False,
        'White', 'Black', 'Nousee (normaali)', False,
        True
    )
    pretty_print('Bridge (main.py style) mapping', bridge_main)


if __name__ == '__main__':
    main()
