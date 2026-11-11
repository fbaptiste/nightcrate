"""Deterministic synthetic catalog and project library for gallery tests/tools."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from nightcrate.catalog_loader.designations import normalize_designation


@dataclass(frozen=True)
class LibraryDsos:
    ids: dict[str, int]

    @property
    def all_ids(self) -> list[int]:
        return list(self.ids.values())

    @property
    def inactive_id(self) -> int:
        return self.ids["inactive"]


@dataclass(frozen=True)
class LibrarySummary:
    expected_visible: int
    visible_by_status: dict[str, int]
    project_ids: list[int] = field(default_factory=list)
    main_images: dict[int, int] = field(default_factory=dict)
    solved_project_ids: list[int] = field(default_factory=list)
    solve_non_target_dsos: dict[int, list[int]] = field(default_factory=dict)
    solve_ids: dict[int, int] = field(default_factory=dict)
    known_project_ids: dict[str, int] = field(default_factory=dict)


_NAMED_DSOS = (
    ("m1", "M 1", "messier", "1", "SNR", "Tau", "Crab Nebula"),
    ("m13", "M 13", "messier", "13", "GCl", "Her", "Hercules Cluster"),
    ("m31", "M 31", "messier", "31", "G", "And", "Andromeda Galaxy"),
    ("m32", "M 32", "messier", "32", "G", "And", None),
    ("m42", "M 42", "messier", "42", "HII", "Ori", "Orion Nebula"),
    ("ngc6992", "NGC 6992", "ngc", "6992", "SNR", "Cyg", "Eastern Veil Nebula"),
    ("ic1795", "IC 1795", "ic", "1795", "HII", "Cas", "Fish Head Nebula"),
    ("inactive", "Sh2-240", "sharpless2", "240", "SNR", "Tau", "Spaghetti Nebula"),
    ("m65", "M 65", "messier", "65", "G", "Leo", None),
    ("m66", "M 66", "messier", "66", "G", "Leo", None),
    ("ngc3628", "NGC 3628", "ngc", "3628", "G", "Leo", "Hamburger Galaxy"),
    ("ic2729", "IC 2729", "ic", "2729", "G", "Leo", None),
    ("m84", "M 84", "messier", "84", "G", "Vir", None),
    ("m86", "M 86", "messier", "86", "G", "Vir", None),
    ("m87", "M 87", "messier", "87", "G", "Vir", "Virgo A"),
    ("ngc4435", "NGC 4435", "ngc", "4435", "G", "Vir", "Eyes"),
    ("ngc4438", "NGC 4438", "ngc", "4438", "G", "Vir", "Eyes"),
)

_KNOWN_GEOMETRY = {
    "m65": (169.733154, 13.092212, 7.64, 1.97, 173.0),
    "m66": (170.062365, 12.991289, 10.28, 4.61, 168.0),
    "ngc3628": (170.070817, 13.5899, 11.04, 3.44, 104.0),
    "ic2729": (170.0276, 13.4088, 0.43, 0.23, 177.0),
    "m84": (186.265597, 12.886983, 7.41, 6.44, 133.0),
    "m86": (186.549225, 12.945969, 11.53, 8.43, 128.0),
    "m87": (187.70593, 12.391123, 7.11, 6.67, 153.0),
    "ngc4435": (186.919708, 13.079896, 3.03, 2.14, 12.0),
    "ngc4438": (186.940913, 13.009734, 9.16, 4.02, 27.0),
}

_KNOWN_ALIASES = {
    "m65": (("ngc", "3623", "NGC 3623"),),
    "m66": (("ngc", "3627", "NGC 3627"),),
    "ngc3628": (("pgc", "34697", "PGC 34697"), ("ugc", "6350", "UGC 6350")),
    "ic2729": (("pgc", "1430330", "PGC 1430330"),),
    "m84": (("ngc", "4374", "NGC 4374"),),
    "m86": (("ngc", "4406", "NGC 4406"),),
    "m87": (("ngc", "4486", "NGC 4486"),),
}


async def make_library_dsos(conn: Any) -> LibraryDsos:
    """Insert a compact multi-catalog DSO set, including one inactive object."""
    source = await conn.execute(
        """
        INSERT INTO dso_catalog_source
            (source_id, category, display_name, file_path, file_hash)
        VALUES ('gallery-tests', 'nightcrate', 'Gallery tests', '/synthetic/catalog', 'gallery')
        """
    )
    source_id = int(source.lastrowid)
    ids: dict[str, int] = {}

    rows = list(_NAMED_DSOS)
    extra_catalogs = ("ngc", "ic", "sharpless2", "caldwell", "lbn")
    extra_types = ("G", "HII", "OCl", "GCl", "RfN", "DrkN", "PN")
    constellations = ("Ori", "Cyg", "Cas", "And", "Per", "Cep")
    for index in range(32):
        catalog = extra_catalogs[index % len(extra_catalogs)]
        identifier = str(8000 + index)
        prefix = {
            "ngc": "NGC",
            "ic": "IC",
            "sharpless2": "Sh2-",
            "caldwell": "C",
            "lbn": "LBN",
        }[catalog]
        separator = "" if prefix.endswith("-") else " "
        display = f"{prefix}{separator}{identifier}"
        rows.append(
            (
                f"extra_{index}",
                display,
                catalog,
                identifier,
                extra_types[index % len(extra_types)],
                constellations[index % len(constellations)],
                f"Synthetic object {index}" if index % 4 == 0 else None,
            )
        )

    for index, (key, display, catalog, identifier, obj_type, constellation, common) in enumerate(
        rows
    ):
        geometry = _KNOWN_GEOMETRY.get(key)
        ra_deg, dec_deg = (
            (geometry[0], geometry[1])
            if geometry is not None
            else (float((index * 9) % 360), float(-45 + (index * 7) % 90))
        )
        dso = await conn.execute(
            """
            INSERT INTO dso (
                primary_designation, obj_type, ra_deg, dec_deg, constellation,
                common_name, source_catalog_id, source_row_hash, source_key, active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                display,
                obj_type,
                ra_deg,
                dec_deg,
                constellation,
                common,
                source_id,
                f"gallery-{index}",
                key,
                0 if key == "inactive" else 1,
            ),
        )
        dso_id = int(dso.lastrowid)
        ids[key] = dso_id
        await conn.execute(
            """
            INSERT INTO dso_designation
                (dso_id, catalog, identifier, display_form, search_key, is_primary)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (dso_id, catalog, identifier, display, normalize_designation(display)),
        )
        if geometry is not None:
            await conn.execute(
                """
                UPDATE dso
                SET maj_axis_arcmin = ?, min_axis_arcmin = ?, position_angle_deg = ?
                WHERE id = ?
                """,
                (*geometry[2:], dso_id),
            )
        for alias_catalog, alias_identifier, alias_display in _KNOWN_ALIASES.get(key, ()):
            await conn.execute(
                """
                INSERT INTO dso_designation
                    (dso_id, catalog, identifier, display_form, search_key, is_primary)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (
                    dso_id,
                    alias_catalog,
                    alias_identifier,
                    alias_display,
                    normalize_designation(alias_display),
                ),
            )

    # Cross-designations and display-ordered names exercise gallery hover data.
    await conn.execute(
        """
        INSERT INTO dso_designation
            (dso_id, catalog, identifier, display_form, search_key, is_primary)
        VALUES (?, 'ngc', '224', 'NGC 224', 'ngc224', 0)
        """,
        (ids["m31"],),
    )
    await conn.execute(
        "INSERT INTO dso_other_name (dso_id, name, position) VALUES (?, ?, 1)",
        (ids["m42"], "Great Orion Nebula"),
    )

    group = await conn.execute(
        """
        INSERT INTO dso_group (catalog, identifier, display_form, search_key, common_name)
        VALUES ('arp', '244', 'Arp 244', 'arp244', 'Antennae Galaxies')
        """
    )
    for dso_id in (ids["extra_0"], ids["extra_1"]):
        await conn.execute(
            "INSERT INTO dso_group_member (group_id, dso_id) VALUES (?, ?)",
            (group.lastrowid, dso_id),
        )
    await conn.commit()
    return LibraryDsos(ids=ids)


async def populate_gallery_projects(
    conn: Any,
    dso_ids: list[int],
    *,
    n_projects: int = 500,
    seed: int = 46,
) -> LibrarySummary:
    """Insert a deterministic, varied gallery library into an existing database."""
    if not dso_ids:
        raise ValueError("At least one DSO is required")
    if n_projects < 0:
        raise ValueError("Project count cannot be negative")

    rng = random.Random(seed)
    rigs: list[int] = []
    for index in range(4):
        cursor = await conn.execute(
            """
            INSERT INTO rig (
                name, telescope_configuration_id, camera_id, active, sort_order
            ) VALUES (?, 1, 1, ?, ?)
            """,
            (f"Gallery Synthetic {seed} Rig {index + 1}", 0 if index == 3 else 1, index),
        )
        rigs.append(int(cursor.lastrowid))

    statuses = ("active", "paused", "complete", "abandoned")
    visible_by_status = {status: 0 for status in statuses}
    project_ids: list[int] = []
    main_images: dict[int, int] = {}
    solved_project_ids: list[int] = []
    solve_non_target_dsos: dict[int, list[int]] = {}
    solve_ids: dict[int, int] = {}
    known_project_ids: dict[str, int] = {}
    session_dates = (
        "2024-12-20",
        "2025-01-03T22:14:00",
        "2025-06-18",
        "2025-10-12",
        "2025-11-03",
        None,
        "spring 2024",
        "2025-02-30",
    )

    for index in range(n_projects):
        status = statuses[index % len(statuses)]
        retired = index % 11 == 0
        name = f"Gallery project {index + 1:04d}"
        if index < 3:
            name = f"Gallery project {index + 1:04d} " + "with an exceptionally long name " * 5
            name = name[:120]
        project = await conn.execute(
            "INSERT INTO project (name, status, active) VALUES (?, ?, ?)",
            (name, status, 0 if retired else 1),
        )
        project_id = int(project.lastrowid)
        project_ids.append(project_id)
        if not retired:
            visible_by_status[status] += 1

        if index % 10 != 0:
            image = await conn.execute(
                """
                INSERT INTO project_image (project_id, file_path, is_main)
                VALUES (?, ?, 1)
                """,
                (project_id, f"/synthetic/gallery/project-{index + 1}.jpg"),
            )
            main_images[project_id] = int(image.lastrowid)

        target_count = min(len(dso_ids), 8 if index < 2 else 1 + index % 3)
        target_start = rng.randrange(len(dso_ids))
        project_targets = [
            dso_ids[(target_start + offset) % len(dso_ids)] for offset in range(target_count)
        ]
        for offset, dso_id in enumerate(project_targets):
            await conn.execute(
                """
                INSERT INTO project_target (project_id, dso_id, created_at)
                VALUES (?, ?, ?)
                """,
                (project_id, dso_id, f"2026-01-01 00:00:{offset:02d}"),
            )

        if project_id in main_images:
            target_cursor = await conn.execute(
                "SELECT ra_deg, dec_deg FROM dso WHERE id = ?", (project_targets[0],)
            )
            target_row = await target_cursor.fetchone()
            solve = await conn.execute(
                """
                INSERT INTO project_solve (
                    project_id, image_path, image_width, image_height,
                    center_ra_deg, center_dec_deg, pixel_scale_arcsec,
                    rotation_deg, fov_width_arcmin, fov_height_arcmin,
                    cd1_1, cd1_2, cd2_1, cd2_2, crpix1, crpix2
                ) VALUES (?, ?, 3000, 2000, ?, ?, 1.44, 0, 72, 48,
                          -0.0004, 0, 0, -0.0004, 1501, 1001)
                """,
                (
                    project_id,
                    f"/synthetic/gallery/solve-{project_id}.fits",
                    float(target_row["ra_deg"]),
                    float(target_row["dec_deg"]),
                ),
            )
            target_set = set(project_targets)
            candidates = [dso_id for dso_id in dso_ids if dso_id not in target_set]
            desired_total = max(len(project_targets) + 1, 3 + index % 4)
            non_targets = rng.sample(
                candidates,
                min(len(candidates), desired_total - len(project_targets)),
            )
            for dso_id in [*project_targets, *non_targets]:
                await conn.execute(
                    "INSERT INTO project_dso (solve_id, dso_id) VALUES (?, ?)",
                    (solve.lastrowid, dso_id),
                )
            solved_project_ids.append(project_id)
            solve_ids[project_id] = int(solve.lastrowid)
            solve_non_target_dsos[project_id] = non_targets

        declared_rig_count = 4 if index < 2 else 1 + (index % 2)
        for rig_id in rigs[:declared_rig_count]:
            await conn.execute(
                "INSERT INTO project_rig (project_id, rig_id) VALUES (?, ?)",
                (project_id, rig_id),
            )

        for session_index in range(3 + index % 8):
            session_rig = rigs[(index + session_index) % len(rigs)]
            await conn.execute(
                """
                INSERT INTO project_session (
                    project_id, rig_id, line_name, exposure_seconds, num_subs,
                    session_date, source
                ) VALUES (?, ?, 'Ha', ?, ?, ?, ?)
                """,
                (
                    project_id,
                    session_rig,
                    float(60 * (1 + (index + session_index) % 10)),
                    1 + (index * 3 + session_index) % 20,
                    session_dates[(index + session_index) % len(session_dates)],
                    "auto" if session_index % 2 else "manual",
                ),
            )

    designation_keys = {
        key: normalize_designation(display)
        for key, display in {
            "m65": "M 65",
            "m66": "M 66",
            "ngc3628": "NGC 3628",
            "m84": "M 84",
            "m86": "M 86",
        }.items()
    }
    known_ids: dict[str, int] = {}
    for key, search_key in designation_keys.items():
        cursor = await conn.execute(
            """
            SELECT d.id
            FROM dso d
            JOIN dso_designation dd ON dd.dso_id = d.id
            WHERE dd.search_key = ? AND d.active = 1
            ORDER BY d.id LIMIT 1
            """,
            (search_key,),
        )
        row = await cursor.fetchone()
        if row is not None:
            known_ids[key] = int(row["id"])

    known_fields = (
        ("leo", "Leo Triplet", 169.93, 13.27, 1.50, ("m65", "m66")),
        ("hamburger", "Hamburger Galaxy", 170.071, 13.589, 0.42, ("ngc3628",)),
        ("markarian", "Markarian's Chain", 186.78, 13.06, 2.30, ("m84", "m86")),
    )
    if all(key in known_ids for field in known_fields for key in field[5]):
        for key, name, ra_deg, dec_deg, field_deg, target_keys in known_fields:
            project = await conn.execute(
                "INSERT INTO project (name, status, active) VALUES (?, 'active', 1)", (name,)
            )
            project_id = int(project.lastrowid)
            known_project_ids[key] = project_id
            project_ids.append(project_id)
            visible_by_status["active"] += 1
            for dso_key in target_keys:
                await conn.execute(
                    "INSERT INTO project_target (project_id, dso_id) VALUES (?, ?)",
                    (project_id, known_ids[dso_key]),
                )
            image = await conn.execute(
                "INSERT INTO project_image (project_id, file_path, is_main) VALUES (?, ?, 1)",
                (project_id, f"/synthetic/gallery/{key}.jpg"),
            )
            main_images[project_id] = int(image.lastrowid)
            scale_deg = field_deg / 1200.0
            solve = await conn.execute(
                """
                INSERT INTO project_solve (
                    project_id, image_path, image_width, image_height,
                    center_ra_deg, center_dec_deg, pixel_scale_arcsec,
                    rotation_deg, fov_width_arcmin, fov_height_arcmin,
                    cd1_1, cd1_2, cd2_1, cd2_2, crpix1, crpix2
                ) VALUES (?, ?, 1200, 900, ?, ?, ?, 0, ?, ?, ?, 0, 0, ?, 601, 451)
                """,
                (
                    project_id,
                    f"/synthetic/gallery/{key}.fits",
                    ra_deg,
                    dec_deg,
                    scale_deg * 3600.0,
                    field_deg * 60.0,
                    field_deg * 45.0,
                    -scale_deg,
                    -scale_deg,
                ),
            )
            solved_project_ids.append(project_id)
            solve_ids[project_id] = int(solve.lastrowid)
            solve_non_target_dsos[project_id] = []

        unsolved = await conn.execute(
            "INSERT INTO project (name, status, active) VALUES ('Unsolved Hamburger', 'active', 1)"
        )
        unsolved_id = int(unsolved.lastrowid)
        known_project_ids["unsolved_hamburger"] = unsolved_id
        project_ids.append(unsolved_id)
        visible_by_status["active"] += 1
        await conn.execute(
            "INSERT INTO project_target (project_id, dso_id) VALUES (?, ?)",
            (unsolved_id, known_ids["ngc3628"]),
        )

    await conn.commit()
    return LibrarySummary(
        expected_visible=sum(visible_by_status.values()),
        visible_by_status=visible_by_status,
        project_ids=project_ids,
        main_images=main_images,
        solved_project_ids=solved_project_ids,
        solve_non_target_dsos=solve_non_target_dsos,
        solve_ids=solve_ids,
        known_project_ids=known_project_ids,
    )
