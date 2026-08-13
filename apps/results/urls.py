from django.urls import path

from . import views

app_name = 'results'

urlpatterns = [
    path('grade-bands/', views.GradeBandListView.as_view(), name='grade_band_list'),
    path('grade-bands/create/', views.GradeBandCreateView.as_view(), name='grade_band_create'),
    path('grade-bands/<uuid:pk>/edit/', views.GradeBandUpdateView.as_view(), name='grade_band_update'),
    path('grade-bands/<uuid:pk>/delete/', views.GradeBandDeleteView.as_view(), name='grade_band_delete'),

    path('my-courses/', views.LecturerOfferingListView.as_view(), name='lecturer_offerings'),
    path('my-courses/<uuid:pk>/class-list/', views.ClassListView.as_view(), name='class_list'),
    path('my-courses/<uuid:pk>/class-list/export/', views.ClassListExportView.as_view(), name='class_list_export'),
    path('my-courses/<uuid:pk>/grades/', views.GradeEntryView.as_view(), name='grade_entry'),
    path('my-courses/<uuid:pk>/grades/submit/', views.SubmitGradesView.as_view(), name='submit_grades'),

    path('review/', views.GradeReviewListView.as_view(), name='grade_review_list'),
    path('review/<uuid:pk>/approve/', views.ApproveGradeView.as_view(), name='approve_grade'),
    path('review/<uuid:pk>/reject/', views.RejectGradeView.as_view(), name='reject_grade'),

    path('collation/', views.GradeCollationListView.as_view(), name='grade_collation_list'),
    path('collation/<uuid:pk>/unlock/', views.UnlockGradeView.as_view(), name='unlock_grade'),

    path('compile/', views.ApprovedGradeListView.as_view(), name='approved_grade_list'),
    path('compile/<uuid:pk>/publish/', views.PublishGradesView.as_view(), name='publish_grades'),
    path('compile/<uuid:pk>/broadsheet/', views.BroadsheetPDFView.as_view(), name='broadsheet_pdf'),
    path('compile/<uuid:pk>/broadsheet/export/', views.BroadsheetCSVExportView.as_view(), name='broadsheet_csv'),

    path('master-broadsheet/', views.MasterBroadsheetView.as_view(), name='master_broadsheet'),
    path('master-broadsheet/export/', views.MasterBroadsheetExportView.as_view(), name='master_broadsheet_export'),

    path('my-results/', views.MyResultsView.as_view(), name='my_results'),
    path('my-score-sheet/', views.MyScoreSheetView.as_view(), name='my_score_sheet'),
    path('my-transcript/', views.MyTranscriptPDFView.as_view(), name='my_transcript'),

    path('transcripts/', views.TranscriptSearchView.as_view(), name='transcript_search'),
    path('transcripts/<uuid:pk>/', views.StudentTranscriptPDFView.as_view(), name='student_transcript'),
]
