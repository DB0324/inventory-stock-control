"""CSV import and export endpoints (goal 7).

Manager-only. An import writes items and stock, which is exactly the set of
things goal 1 reserves for managers -- doing it a hundred rows at a time does
not change who is allowed to.
"""

import csv

from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.api import csv_io
from apps.api.permissions import IsManager


class _Echo:
    """A file-like object whose write() returns the line instead of storing it.

    The standard trick for streaming csv: the writer thinks it is writing to a
    file, and each row comes back to be yielded.
    """

    def write(self, value):
        return value


def _run(request, importer):
    upload = request.FILES.get("file")
    if upload is None:
        return Response(
            {"detail": "Attach a CSV file as 'file'."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        report = importer(file=upload, actor=request.user)
    except csv_io.CsvFormatError as exc:
        # The file itself is unusable, which is a different answer from "some
        # rows failed" and deserves a different status.
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    # 200 even when some rows failed. The request succeeded and the report is
    # the result; a 4xx would suggest nothing was imported, which is wrong.
    return Response(report)


@api_view(["POST"])
@permission_classes([IsManager])
@parser_classes([MultiPartParser])
def import_items(request):
    return _run(request, csv_io.import_items)


@api_view(["POST"])
@permission_classes([IsManager])
@parser_classes([MultiPartParser])
def import_receipts(request):
    return _run(request, csv_io.import_receipts)


@api_view(["GET"])
@permission_classes([IsManager])
def export_stock_position(request):
    writer = csv.writer(_Echo())
    stamp = timezone.localtime().date().isoformat()
    response = StreamingHttpResponse(
        (writer.writerow(row) for row in csv_io.export_stock_position()),
        content_type="text/csv",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="stock-position-{stamp}.csv"'
    )
    return response
