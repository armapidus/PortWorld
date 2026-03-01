import SwiftUI

struct TipRowView: View {
  let resource: ImageResource
  let title: String?
  let text: String
  let iconColor: Color
  let titleColor: Color
  let textColor: Color

  init(
    resource: ImageResource,
    title: String? = nil,
    text: String,
    iconColor: Color,
    titleColor: Color,
    textColor: Color
  ) {
    self.resource = resource
    self.title = title
    self.text = text
    self.iconColor = iconColor
    self.titleColor = titleColor
    self.textColor = textColor
  }

  var body: some View {
    HStack(alignment: .top, spacing: 12) {
      Image(resource)
        .resizable()
        .renderingMode(.template)
        .foregroundColor(iconColor)
        .aspectRatio(contentMode: .fit)
        .frame(width: 24)
        .padding(.leading, 4)
        .padding(.top, 4)

      if let title {
        VStack(alignment: .leading, spacing: 6) {
          Text(title)
            .font(.system(size: 18, weight: .semibold))
            .foregroundColor(titleColor)

          Text(text)
            .font(.system(size: 15))
            .foregroundColor(textColor)
        }
      } else {
        Text(text)
          .font(.system(size: 15))
          .foregroundColor(textColor)
          .fixedSize(horizontal: false, vertical: true)
      }

      Spacer()
    }
    .frame(maxWidth: .infinity, alignment: .leading)
  }
}
