"""Correct saved standard-image solves to NightCrate's top-down row order."""

import math

from yoyo import step

__depends__ = {"0063.dso_source_key"}


def _apply(conn) -> None:
    rows = conn.execute(
        """
        SELECT id, image_height, crpix2, cd1_2, cd2_2
        FROM project_solve
        WHERE instr(image_path, '::') = 0
          AND (
              lower(image_path) LIKE '%.png'
              OR lower(image_path) LIKE '%.jpg'
              OR lower(image_path) LIKE '%.jpeg'
              OR lower(image_path) LIKE '%.tif'
              OR lower(image_path) LIKE '%.tiff'
          )
          AND image_height IS NOT NULL
          AND crpix2 IS NOT NULL
          AND cd1_2 IS NOT NULL
          AND cd2_2 IS NOT NULL
        """
    ).fetchall()

    for solve_id, image_height, crpix2, cd1_2, cd2_2 in rows:
        new_crpix2 = image_height + 1 - crpix2
        new_cd1_2 = -cd1_2
        new_cd2_2 = -cd2_2
        rotation_deg = math.degrees(math.atan2(-new_cd1_2, new_cd2_2))
        conn.execute(
            """
            UPDATE project_solve
            SET crpix2 = ?, cd1_2 = ?, cd2_2 = ?, rotation_deg = ?
            WHERE id = ?
            """,
            (new_crpix2, new_cd1_2, new_cd2_2, rotation_deg, solve_id),
        )


steps = [step(_apply)]
