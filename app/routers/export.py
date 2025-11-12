from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_
from uuid import UUID
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from io import BytesIO, StringIO
import csv
from typing import List
from pydantic import BaseModel

from app.database import get_db
from app.models import Event, Contact, User
from app.auth import get_current_user

router = APIRouter(tags=["export"])


@router.get("/event/{event_id}/pdf")
async def export_event_pdf(
    event_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Export event contacts to PDF"""
    # Get event
    event = db.query(Event).filter(
        Event.id == event_id,
        Event.user_id == current_user.id
    ).first()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    # Get contacts
    contacts = db.query(Contact).filter(
        Contact.event_id == event_id,
        Contact.user_id == current_user.id
    ).order_by(Contact.meeting_date.desc()).all()

    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []

    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#667eea'),
        spaceAfter=30
    )

    # Title
    elements.append(Paragraph(event.name, title_style))
    elements.append(Spacer(1, 0.2 * inch))

    # Event details
    details = [
        f"<b>Location:</b> {event.location}",
        f"<b>Dates:</b> {event.start_date.strftime('%B %d, %Y')} - {event.end_date.strftime('%B %d, %Y')}"
    ]
    if event.description:
        details.append(f"<b>Description:</b> {event.description}")

    for detail in details:
        elements.append(Paragraph(detail, styles['Normal']))
        elements.append(Spacer(1, 0.1 * inch))

    elements.append(Spacer(1, 0.3 * inch))

    # Contacts table
    if contacts:
        table_data = [['Name', 'Email', 'Role/Company', 'Mobile', 'Date Met']]

        for contact in contacts:
            tags_str = ', '.join([tag.name for tag in contact.tags]) if contact.tags else '-'
            table_data.append([
                contact.name or '-',
                contact.email or '-',
                contact.role_company or '-',
                contact.mobile or '-',
                contact.meeting_date.strftime('%Y-%m-%d') if contact.meeting_date else '-'
            ])

        table = Table(table_data, colWidths=[1.5*inch, 1.8*inch, 1.5*inch, 1.2*inch, 1*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
        ]))

        elements.append(table)
    else:
        elements.append(Paragraph("No contacts found for this event.", styles['Normal']))

    # Build PDF
    doc.build(elements)
    buffer.seek(0)

    # Return PDF
    filename = f"{event.name.replace(' ', '_')}_contacts.pdf"
    return Response(
        content=buffer.read(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/event/{event_id}/csv")
async def export_event_csv(
    event_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Export event contacts to CSV"""
    # Get event
    event = db.query(Event).filter(
        Event.id == event_id,
        Event.user_id == current_user.id
    ).first()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    # Get contacts
    contacts = db.query(Contact).filter(
        Contact.event_id == event_id,
        Contact.user_id == current_user.id
    ).order_by(Contact.meeting_date.desc()).all()

    # Create CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Name', 'Email', 'Role/Company', 'Mobile', 'LinkedIn', 
        'Meeting Date', 'Meeting Context', 'Tags', 'Event'
    ])
    
    # Write contact data
    for contact in contacts:
        tags_str = ', '.join([tag.name for tag in contact.tags]) if contact.tags else ''
        writer.writerow([
            contact.name or '',
            contact.email or '',
            contact.role_company or '',
            contact.mobile or '',
            contact.linkedin_url or '',
            contact.meeting_date.strftime('%Y-%m-%d %H:%M:%S') if contact.meeting_date else '',
            contact.meeting_context or '',
            tags_str,
            event.name
        ])
    
    # Get CSV content
    csv_content = output.getvalue()
    output.close()
    
    # Return CSV
    filename = f"{event.name.replace(' ', '_')}_contacts.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


class ContactExportRequest(BaseModel):
    contact_ids: List[UUID]


@router.post("/contacts/pdf")
async def export_contacts_pdf(
    request: ContactExportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Export selected contacts to PDF"""
    if not request.contact_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No contact IDs provided"
        )

    # Get contacts with relationships
    contacts = db.query(Contact).options(
        joinedload(Contact.tags),
        joinedload(Contact.event)
    ).filter(
        and_(
            Contact.id.in_(request.contact_ids),
            Contact.user_id == current_user.id
        )
    ).order_by(Contact.meeting_date.desc()).all()

    if not contacts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No contacts found"
        )

    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []

    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#667eea'),
        spaceAfter=30
    )

    # Title
    elements.append(Paragraph(f"Selected Contacts ({len(contacts)})", title_style))
    elements.append(Spacer(1, 0.2 * inch))

    # Contacts table
    table_data = [['Name', 'Email', 'Role/Company', 'Mobile', 'Date Met', 'Tags']]

    for contact in contacts:
        tags_str = ', '.join([tag.name for tag in contact.tags]) if contact.tags else '-'
        table_data.append([
            contact.name or '-',
            contact.email or '-',
            contact.role_company or '-',
            contact.mobile or '-',
            contact.meeting_date.strftime('%Y-%m-%d') if contact.meeting_date else '-',
            tags_str
        ])

    table = Table(table_data, colWidths=[1.3*inch, 1.6*inch, 1.3*inch, 1.1*inch, 1*inch, 1.2*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
    ]))

    elements.append(table)

    # Build PDF
    doc.build(elements)
    buffer.seek(0)

    # Return PDF
    filename = f"contacts_export_{len(contacts)}_contacts.pdf"
    return Response(
        content=buffer.read(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.post("/contacts/csv")
async def export_contacts_csv(
    request: ContactExportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Export selected contacts to CSV"""
    if not request.contact_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No contact IDs provided"
        )

    # Get contacts with relationships
    contacts = db.query(Contact).options(
        joinedload(Contact.tags),
        joinedload(Contact.event)
    ).filter(
        and_(
            Contact.id.in_(request.contact_ids),
            Contact.user_id == current_user.id
        )
    ).order_by(Contact.meeting_date.desc()).all()

    if not contacts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No contacts found"
        )

    # Create CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Name', 'Email', 'Role/Company', 'Mobile', 'LinkedIn', 
        'Meeting Date', 'Meeting Context', 'Tags', 'Event'
    ])
    
    # Write contact data
    for contact in contacts:
        tags_str = ', '.join([tag.name for tag in contact.tags]) if contact.tags else ''
        event_name = contact.event.name if contact.event else ''
        writer.writerow([
            contact.name or '',
            contact.email or '',
            contact.role_company or '',
            contact.mobile or '',
            contact.linkedin_url or '',
            contact.meeting_date.strftime('%Y-%m-%d %H:%M:%S') if contact.meeting_date else '',
            contact.meeting_context or '',
            tags_str,
            event_name
        ])
    
    # Get CSV content
    csv_content = output.getvalue()
    output.close()
    
    # Return CSV
    filename = f"contacts_export_{len(contacts)}_contacts.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

